import json
import os
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError

import requests
from redis.client import Redis

from oql.util import queries_equal

REDIS_CLIENT = Redis.from_url(os.environ.get("REDIS_DO_URL"))

EXECUTOR = ThreadPoolExecutor(max_workers=os.environ.get("TEST_THREADS_PER_DYNO", 100))
HARD_TIMEOUT = 2*60
DEFAULT_JOB_TIMEOUT = 3*60


def decode_redis_data(data):
    decoded_data = {}
    for key, value in data.items():
        decoded_key = key.decode('utf-8')
        decoded_value = value.decode(
            'utf-8')

        try:
            decoded_value = json.loads(decoded_value)
        except json.JSONDecodeError:
            pass

        decoded_data[decoded_key] = decoded_value

    return decoded_data


def process_query_test(test):
    search_id = None

    def create_search(query):
        json_obj = {
            'query': query,
            'mailto': 'team@ourresearch.org'
        }
        r = requests.post("https://api.openalex.org/analytics", json=json_obj)
        r.raise_for_status()
        return r.json()['id']

    def get_search_state(search_id):
        url = f"https://api.openalex.org/analytics/{search_id}"
        params = {'mailto': 'team@ourresearch.org'}
        r = requests.get(url, params=params)
        r.raise_for_status()
        return r.json()

    try:
        search_id = create_search(test['query'])
        timeout = test.get('searchTimeout', 30)
        start_time = time.time()
        while True:
            result = get_search_state(search_id)
            if result['is_ready']:
                elapsed_time = time.time() - start_time
                passing = len(result['results']) > 0
                results_json = json.dumps(result['results'])
                if 'resultsContain' in test:
                    if isinstance(test['resultsContain'], list):
                        passing = passing and all([substr in results_json for substr in test['resultsContain']])
                    elif isinstance(test['resultsContain'], str):
                        passing = passing and test['resultsContain'] in results_json
                return {
                    'id': test['test_id'],
                    'case': 'queryToSearch',
                    'isPassing': passing,
                    'details': {
                        'searchId': search_id,
                        'elapsedTime': elapsed_time,
                        'resultsCount': len(result['results']),
                    }
                }
            if time.time() - start_time >= timeout or time.time() - start_time >= HARD_TIMEOUT:
                return {
                    'id': test['test_id'],
                    'case': 'queryToSearch',
                    'isPassing': False,
                    'details': {
                        'searchId': search_id,
                        'error': 'timeout',
                        'test': test
                    }
                }
            time.sleep(1)
    except Exception as e:
        return {
            'id': test['test_id'],
            'case': 'queryToSearch',
            'isPassing': False,
            'details': {
                'searchId': search_id,
                'error': str(e),
                'test': test
            }
        }


def process_nat_lang_test(test):
    params = {
        'natural_language': test['prompt'],
        'mailto': 'team@ourresearch.org'
    }
    try:
        r = requests.get('https://api.openalex.org/text/oql', params=params, timeout=HARD_TIMEOUT)
        r.raise_for_status()
        oqo = r.json()
        passing = queries_equal(oqo, test['query'])
        result = {
            'id': test['test_id'],
            'case': 'natLang',
            'isPassing': passing,
            'prompt': test['prompt'],
            'details': {
                'expected': test['query'],
                'actual': oqo,
            },
        }
        result['details'].update(passing)
    except Exception as e:
        return {
            'id': test['test_id'],
            'case': 'natLang',
            'isPassing': False,
            'prompt': test['prompt'],
            'error': str(e)
        }


def process_test(test):
    if 'query' in test:
        return process_query_test(test)
    elif 'prompt' in test:
        return process_nat_lang_test(test)
    else:
        return {'error': 'Invalid test format', 'test': test}


def process_job(job_id):
    try:
        print(f'Processing job: {job_id}')
        job = REDIS_CLIENT.hgetall(f'job:{job_id}')
        job = decode_redis_data(job)
        job_timeout = job.get('timeout', DEFAULT_JOB_TIMEOUT)

        REDIS_CLIENT.hset(f'job:{job_id}', 'status', 'processing')

        tests = job['tests']
        results = []
        futures = {}

        start_time = time.time()

        # Submit all tests to the executor
        for test in tests:
            future = EXECUTOR.submit(process_test, test)
            futures[future] = test

        # Process completed futures and handle timeout
        while futures:
            try:
                # Wait for the next future to complete, but not longer than the remaining timeout
                time_elapsed = time.time() - start_time
                time_remaining = max(0, job_timeout - time_elapsed)
                print(f'Processing job: {job_id}, time: {time_remaining} seconds')
                completed = as_completed(futures.keys(),
                                            timeout=time_remaining)
                for future in completed:
                    test = futures.pop(future)
                    try:
                        result = future.result()
                        if result['case'] == 'natLang':
                            nat_lang_group = next((r for r in results if
                                                   r['id'] == result['id'] and
                                                   r['case'] == 'natLang'),
                                                  None)
                            if nat_lang_group is None:
                                nat_lang_group = {
                                    'id': result['id'],
                                    'case': 'natLang',
                                    'results': []
                                }
                                results.append(nat_lang_group)
                            nat_lang_group['results'].append(result)
                        else:
                            results.append(result)
                    except Exception as e:
                        error_result = {
                            'id': test.get('test_id', 'unknown'),
                            'case': test.get('case', 'unknown'),
                            'isPassing': False,
                            'details': {
                                'error': str(e),
                                'test': test
                            }
                        }
                        results.append(error_result)

                    # Update results in Redis
                    REDIS_CLIENT.hset(f'job:{job_id}', 'results',
                                      json.dumps(results))

            except TimeoutError:
                # Job timeout reached, mark remaining tests as failed
                for future, test in futures.items():
                    future.cancel()
                    timeout_result = {
                        'id': test.get('test_id', 'unknown'),
                        'case': test.get('case', 'unknown'),
                        'isPassing': False,
                        'details': {
                            'error': 'timeout',
                            'test': test
                        }
                    }
                    if test.get('prompt'):
                        timeout_result['prompt'] = test['prompt']
                    results.append(timeout_result)

                break  # Exit the while loop as we've handled all remaining futures

        # Update job as completed
        REDIS_CLIENT.hset(f'job:{job_id}', mapping={
            'status': 'completed',
            'is_completed': 'true',
            'results': json.dumps(results)
        })
        print(f'Finished processing job: {job_id}')
    except Exception as e:
        traceback.print_exc()
        REDIS_CLIENT.hset(f'job:{job_id}', mapping={
            'status': 'failed',
            'error': str(e)
        })


def run_job_processor():
    while True:
        # Get the next job from the queue
        job_id = REDIS_CLIENT.brpop('job_queue', timeout=1)
        if job_id:
            job_id = job_id[1].decode()
            process_job(job_id)
        else:
            time.sleep(1)  # Wait for 1 second before checking for new jobs


if __name__ == "__main__":
    from app import create_app

    app = create_app()
    with app.app_context():
        try:
            run_job_processor()
        finally:
            # Ensure the executor is shut down properly when the script exits
            EXECUTOR.shutdown(wait=True)
