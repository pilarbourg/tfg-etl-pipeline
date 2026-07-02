from src.app.core.etl.pipeline.extract_pdf import _https_candidates

def test_ftp_url_rewritten_to_https():
    ftp = "ftp://ftp.ncbi.nlm.nih.gov/pub/pmc/oa_package/00/01/PMC123.tar.gz"
    result = _https_candidates(ftp)
    assert all(u.startswith("https://") for u in result)
    assert any("ncbi.nlm.nih.gov" in u for u in result)

def test_https_url_returned_unchanged():
    https = "https://ftp.ncbi.nlm.nih.gov/pub/pmc/oa_package/00/01/PMC123.tar.gz"
    result = _https_candidates(https)
    assert https in result