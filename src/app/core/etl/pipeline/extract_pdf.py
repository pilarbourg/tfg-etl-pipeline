import requests
import os
import logging
import tarfile
import io
import re
from xml.etree import ElementTree as ET

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("pipeline.log"),
        logging.StreamHandler()
    ]
)

UNPAYWALL_EMAIL = os.getenv("UNPAYWALL_EMAIL")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://pmc.ncbi.nlm.nih.gov/",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

def _https_candidates(url: str) -> list[str]:
    """
    Converts FTP link to HTTPS link.
    """
    if not url.startswith("ftp://"):
        return [url]

    plain = url.replace("ftp://", "https://", 1)
    deprecated = plain.replace(
        "https://ftp.ncbi.nlm.nih.gov/pub/pmc/",
        "https://ftp.ncbi.nlm.nih.gov/pub/pmc/deprecated/",
        1,
    )

    candidates = []
    for c in (plain, deprecated):
        if c not in candidates:
            candidates.append(c)
    return candidates


def get_download_info(pmcid: str) -> tuple[str, str] | tuple[None, None]:
    """
    Returns the download methods available (pdf, tgz, none) for a given publication according to PMCID.
    """
    url = f"https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi?id=PMC{pmcid}"
    try:
        response = SESSION.get(url, timeout=30)
        response.raise_for_status()
        root = ET.fromstring(response.content)

        pdf_url = None
        tgz_url = None

        for link in root.iter("link"):
            fmt = link.attrib.get("format")
            href = link.attrib.get("href", "")
            if fmt == "pdf":
                pdf_url = href
            elif fmt == "tgz":
                tgz_url = href

        if pdf_url:
            return pdf_url, "pdf"
        elif tgz_url:
            return tgz_url, "tgz"

        logging.warning(f"No downloadable format found for PMC{pmcid}")
        return None, None

    except Exception as e:
        logging.error(f"Error fetching download info for PMC{pmcid}: {e}")
        return None, None


def get_pdf_url_from_doi(doi: str) -> str | None:
    """
    Checks Unpaywall API for the DOI PDF url.
    """
    try:
        url = f"https://api.unpaywall.org/v2/{doi}?email={UNPAYWALL_EMAIL}"
        response = SESSION.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()

        best = data.get("best_oa_location")
        if best and best.get("url_for_pdf"):
            return best["url_for_pdf"]

        for location in data.get("oa_locations", []):
            if location.get("url_for_pdf"):
                return location["url_for_pdf"]

        logging.warning(f"No PDF URL found in Unpaywall for DOI {doi}")
        return None

    except Exception as e:
        logging.error(f"Error fetching Unpaywall data for DOI {doi}: {e}")
        return None


def _save_pdf_response(content: bytes, save_path: str) -> bool:
    """
    Saves the PDF content to save_path.
    """
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    with open(save_path, "wb") as f:
        f.write(content)
    return True


def _download_pdf_direct(url: str, save_path: str, require_pdf_content_type: bool = False) -> bool:
    """
    Returns True if successful download of the PDF directly from one of the candidate methods.
    """
    for candidate in _https_candidates(url):
        try:
            logging.info(f"Downloading PDF from {candidate}")
            response = SESSION.get(candidate, headers=HEADERS, timeout=60, allow_redirects=True)
            if response.status_code != 200:
                logging.warning(f"PDF fetch returned status {response.status_code} for {candidate}")
                continue
            if require_pdf_content_type and "pdf" not in response.headers.get("Content-Type", "").lower():
                logging.warning(f"Response was not a PDF (Content-Type) for {candidate}")
                continue
            _save_pdf_response(response.content, save_path)
            logging.info(f"Saved to {save_path}")
            return True
        except Exception as e:
            logging.error(f"Error downloading PDF from {candidate}: {e}")
            continue
    return False


def _download_tgz(url: str) -> bytes | None:
    """
    Returns the binary content (bytes) if successfully downloads compressed tgz.
    """
    for candidate in _https_candidates(url):
        try:
            logging.info(f"Downloading tarball from {candidate}")
            response = SESSION.get(candidate, timeout=60)
            if response.status_code == 200:
                return response.content
            logging.warning(f"Tarball fetch returned status {response.status_code} for {candidate}")
        except Exception as e:
            logging.error(f"Error downloading tarball from {candidate}: {e}")
            continue
    logging.error(f"Failed to download tarball from any candidate for {url}")
    return None


def _save_pdf_from_tgz(content: bytes, save_path: str) -> bool:
    """
    Returns true if successfully extracts the PDF from the tgz.
    """
    try:
        with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as tar:
            for member in tar.getmembers():
                if member.name.endswith(".pdf"):
                    f = tar.extractfile(member)
                    if f:
                        os.makedirs(os.path.dirname(save_path), exist_ok=True)
                        with open(save_path, "wb") as out:
                            out.write(f.read())
                        logging.info(f"Extracted PDF from tarball, saved to {save_path}")
                        return True

        logging.error(f"No PDF found inside tarball for {save_path}")
        return False

    except Exception as e:
        logging.error(f"Error extracting tarball: {e}")
        return False


def download_pmc_pdf(pmcid: str, doi: str | None = None) -> bool:
    """
    Returns True if successfully downloads PDF from PMCID
    """
    if not pmcid:
        logging.error("No PMCID provided")
        return False

    save_path = f"downloads/PMC{pmcid}.pdf"

    if os.path.exists(save_path):
        logging.info(f"PMC{pmcid} already downloaded, skipping.")
        return True

    download_url, fmt = get_download_info(pmcid)

    if download_url:
        if fmt == "pdf":
            if _download_pdf_direct(download_url, save_path):
                return True

        elif fmt == "tgz":
            content = _download_tgz(download_url)
            if content:
                return _save_pdf_from_tgz(content, save_path)
            
    if doi:
        pdf_url = get_pdf_url_from_doi(doi)
        if pdf_url:
            if _download_pdf_direct(pdf_url, save_path, require_pdf_content_type=True):
                logging.info(f"Saved {save_path} via Unpaywall")
                return True

    logging.error(f"All download methods failed for PMC{pmcid}")
    return False