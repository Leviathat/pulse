from processor import main


def test_defaults_match_spec() -> None:
    assert main.TOPIC == "raw_articles"
    assert main.GROUP_ID == "pulse-processor"
