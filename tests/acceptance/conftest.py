# Acceptance tests don't use Flask test client - they hit the live API directly.
# This conftest overrides the parent one to prevent app import issues.
