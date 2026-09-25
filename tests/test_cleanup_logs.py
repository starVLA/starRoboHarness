from starharness.rollout.campaign import close_log


def test_diagnostic_io_failure_does_not_replace_episode_failure():
    class BrokenLog:
        def close(self):
            raise OSError(5, "input/output error")

    errors = [{"operation": "primary", "type": "RuntimeError"}]
    close_log(BrokenLog(), errors)
    assert errors == [{"operation": "primary", "type": "RuntimeError"},
                      {"operation": "log.close", "type": "OSError"}]
