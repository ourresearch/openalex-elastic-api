import json
import os
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from redis.client import Redis

redis_client = Redis.from_url(os.environ.get("REDIS_DO_URL"))

executor = ThreadPoolExecutor(max_workers=30)


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
        r = requests.post("https://api.openalex.org/searches", json=json_obj)
        r.raise_for_status()
        return r.json()['id']

    def get_search_state(search_id):
        url = f"https://api.openalex.org/searches/{search_id}"
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
                return {
                    'id': test['test_id'],
                    'case': 'queryToSearch',
                    'isPassing': len(result['results']) > 0,
                    'details': {
                        'searchId': search_id,
                        'elapsedTime': elapsed_time,
                        'resultsCount': len(result['results']),
                    }
                }
            if time.time() - start_time >= timeout:
                return {
                    'id': test['test_id'],
                    'case': 'queryToSearch',
                    'isPassing': False,
                    'details': {
                        'searchId': search_id,
                        'error': 'Search timed out',
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
        r = requests.get('https://api.openalex.org/text/oql', params=params)
        r.raise_for_status()
        oqo = r.json()
        return {
            'id': test['test_id'],
            'case': 'natLang',
            'prompt': test['prompt'],
            'oqo': oqo
        }
    except Exception as e:
        return {
            'id': test['test_id'],
            'case': 'natLang',
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
        # Get the job from Redis
        job = redis_client.hgetall(f'job:{job_id}')
        job = decode_redis_data(job)

        # Update job status
        redis_client.hset(f'job:{job_id}', 'status', 'processing')

        tests = job['tests']
        results = []
        nat_lang_results = {}

        # Use the global executor
        future_to_test = {executor.submit(process_test, test): test for test in
                          tests}
        for future in as_completed(future_to_test):
            test = future_to_test[future]
            try:
                result = future.result()
                if result['case'] == 'natLang':
                    if result['id'] not in nat_lang_results:
                        nat_lang_results[result['id']] = []
                    nat_lang_results[result['id']].append(result)
                else:
                    results.append(result)
            except Exception as e:
                print(f"Test processing failed: {str(e)}")
                results.append({
                    'id': test.get('test_id', 'unknown'),
                    'case': test.get('case', 'unknown'),
                    'isPassing': False,
                    'details': {
                        'error': str(e),
                        'test': test
                    }
                })

        # Group natLang results
        for test_id, nat_lang_tests in nat_lang_results.items():
            results.append({
                'id': test_id,
                'case': 'natLang',
                'results': nat_lang_tests
            })

        # Update job with results
        redis_client.hset(f'job:{job_id}', mapping={
            'status': 'completed',
            'is_completed': 'true',
            'results': json.dumps(results)
        })
        print(f'Finished processing job: {job_id}')
    except Exception as e:
        traceback.print_exc()
        redis_client.hset(f'job:{job_id}', mapping={
            'status': 'failed',
            'error': str(e)
        })


def run_job_processor():
    while True:
        # Get the next job from the queue
        job_id = redis_client.brpop('job_queue', timeout=1)
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
            executor.shutdown(wait=True)
