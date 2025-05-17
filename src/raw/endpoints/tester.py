def run_all_tests(config, user, profile):
            return {"status": "ok", "tests_run": 0}

        def run_tests(endpoint, config, user, profile):
            return {"status": "ok", "tests_run": 1, "endpoint": endpoint}