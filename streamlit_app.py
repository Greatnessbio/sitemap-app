import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlparse
import time
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import threading
from bs4 import BeautifulSoup
import re

# Initialize session state
if 'sitemap_urls' not in st.session_state:
    st.session_state.sitemap_urls = []
if 'content_data' not in st.session_state:
    st.session_state.content_data = []

# User agent to mimic a browser
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# Create a retry strategy
retry_strategy = Retry(
    total=3,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["HEAD", "GET", "OPTIONS"],
    backoff_factor=1
)
adapter = HTTPAdapter(max_retries=retry_strategy)
http = requests.Session()
http.mount("https://", adapter)
http.mount("http://", adapter)

# Rate limiting setup
RATE_LIMIT = 20  # requests per minute
RATE_LIMIT_PERIOD = 60  # seconds
DELAY_BETWEEN_REQUESTS = 3  # seconds

class RateLimiter:
    def __init__(self, max_calls, period):
        self.max_calls = max_calls
        self.period = period
        self.calls = []
        self.lock = threading.Lock()

    def __call__(self, f):
        def wrapped(*args, **kwargs):
            with self.lock:
                now = time.time()
                # Remove calls older than the period
                self.calls = [c for c in self.calls if c > now - self.period]
                if len(self.calls) >= self.max_calls:
                    sleep_time = self.calls[0] - (now - self.period)
                    time.sleep(sleep_time)
                self.calls.append(time.time())
            return f(*args, **kwargs)
        return wrapped

rate_limiter = RateLimiter(RATE_LIMIT, RATE_LIMIT_PERIOD)

def check_password():
    """Returns `True` if the user had the correct password."""
    def password_entered():
        if st.session_state["password"] == st.secrets["password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input(
            "Password", type="password", on_change=password_entered, key="password"
        )
        return False
    elif not st.session_state["password_correct"]:
        st.text_input(
            "Password", type="password", on_change=password_entered, key="password"
        )
        st.error("😕 Password incorrect")
        return False
    else:
        return True

def get_sitemap_from_robots_txt(url, depth=0):
    if depth > 5:  # Limit recursion depth
        return None
    robots_txt_url = urljoin(url, '/robots.txt')
    try:
        response = http.get(robots_txt_url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        content = response.text
        
        # Check for sitemap in robots.txt content
        sitemap_match = re.search(r'Sitemap:\s*(https?://\S+)', content, re.IGNORECASE)
        if sitemap_match:
            return sitemap_match.group(1)
        
        # Check for XML content
        xml_match = re.search(r'<\?xml.*?>.*?<sitemapindex', content, re.DOTALL)
        if xml_match:
            # Extract URLs from the XML content
            root = ET.fromstring(content[xml_match.start():])
            for sitemap in root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}loc'):
                return sitemap.text  # Return the first sitemap URL found
        
        st.warning(f"No sitemap found in robots.txt from {robots_txt_url}")
    except requests.exceptions.RequestException as e:
        st.warning(f"Failed to fetch robots.txt from {robots_txt_url}: {str(e)}")
    return None

def process_sitemap(content, base_url, depth=0, processed_urls=None):
    if processed_urls is None:
        processed_urls = set()
    if depth > 5:  # Limit recursion depth
        return []
    try:
        root = ET.fromstring(content)
        urls = []
        
        # Check if this is a sitemap index
        sitemaps = root.findall('{http://www.sitemaps.org/schemas/sitemap/0.9}sitemap')
        if sitemaps:
            st.info("This is a sitemap index. Processing individual sitemaps...")
            for sitemap in sitemaps:
                sitemap_url = sitemap.find('{http://www.sitemaps.org/schemas/sitemap/0.9}loc').text
                if sitemap_url not in processed_urls:
                    processed_urls.add(sitemap_url)
                    st.info(f"Fetching sitemap: {sitemap_url}")
                    try:
                        response = http.get(sitemap_url, headers=HEADERS, timeout=10)
                        response.raise_for_status()
                        urls.extend(process_sitemap(response.content, base_url, depth + 1, processed_urls))
                    except requests.exceptions.RequestException as e:
                        st.warning(f"Failed to fetch sitemap from {sitemap_url}: {str(e)}")
        else:
            # This is a regular sitemap, extract URLs
            for url in root.findall('{http://www.sitemaps.org/schemas/sitemap/0.9}url'):
                loc = url.find('{http://www.sitemaps.org/schemas/sitemap/0.9}loc').text
                urls.append(loc)
            st.info(f"Extracted {len(urls)} URLs from sitemap")
        
        return urls
    except ET.ParseError as e:
        st.warning(f"Failed to parse sitemap XML: {str(e)}")
        return []

def scrape_homepage_links(url):
    try:
        response = http.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        links = [urljoin(url, a['href']) for a in soup.find_all('a', href=True) if urljoin(url, a['href']).startswith(url)]
        st.info(f"Extracted {len(links)} links from homepage")
        return links
    except requests.exceptions.RequestException as e:
        st.warning(f"Failed to scrape links from homepage {url}: {str(e)}")
        return []

def get_sitemap_urls(url, depth=0, processed_urls=None):
    if processed_urls is None:
        processed_urls = set()
    if depth > 5 or url in processed_urls:  # Limit recursion depth and avoid loops
        st.warning(f"Reached maximum recursion depth or already processed URL: {url}")
        return []
    
    processed_urls.add(url)
    st.info(f"Attempting to fetch sitemap for {url}")
    
    # First, try to find sitemap URL in robots.txt
    st.info("Attempting to find sitemap URL in robots.txt")
    sitemap_url = get_sitemap_from_robots_txt(url, depth)
    if sitemap_url and sitemap_url not in processed_urls:
        try:
            st.info(f"Found sitemap URL: {sitemap_url}")
            response = http.get(sitemap_url, headers=HEADERS, timeout=10)
            response.raise_for_status()
            st.success(f"Successfully fetched sitemap from {sitemap_url}")
            return process_sitemap(response.content, url, depth, processed_urls)
        except requests.exceptions.RequestException as e:
            st.warning(f"Failed to fetch sitemap from {sitemap_url}: {str(e)}")

    # If robots.txt method fails, try the standard sitemap location
    sitemap_url = urljoin(url, '/sitemap.xml')
    if sitemap_url not in processed_urls:
        try:
            st.info(f"Trying standard sitemap location: {sitemap_url}")
            response = http.get(sitemap_url, headers=HEADERS, timeout=10)
            response.raise_for_status()
            st.success(f"Successfully fetched sitemap from {sitemap_url}")
            return process_sitemap(response.content, url, depth, processed_urls)
        except requests.exceptions.RequestException as e:
            st.warning(f"Failed to fetch sitemap from {sitemap_url}: {str(e)}")

    # If all else fails, scrape links from the homepage
    st.info(f"Sitemap methods failed. Scraping links from the homepage: {url}")
    return scrape_homepage_links(url)

@rate_limiter
def get_jina_reader_content(url):
    jina_url = f"https://r.jina.ai/{url}"
    try:
        response = http.get(jina_url, timeout=10)
        response.raise_for_status()
        time.sleep(DELAY_BETWEEN_REQUESTS)  # Ensure 3-second delay between requests
        return response.text
    except requests.exceptions.RequestException as e:
        return f"Failed to fetch content: {str(e)}"

def main():
    st.title('Web Scraper App with Sitemap and Jina Reader')

    if check_password():
        st.success("Logged in successfully!")

        website = st.text_input('Enter website URL (including http:// or https://):')
        
        if st.button('Fetch Sitemap and Content'):
            if website:
                with st.spinner('Fetching sitemap...'):
                    st.session_state.sitemap_urls = get_sitemap_urls(website)
                
                if st.session_state.sitemap_urls:
                    st.subheader("Sitemap URLs:")
                    sitemap_df = pd.DataFrame({'URL': st.session_state.sitemap_urls})
                    st.dataframe(sitemap_df)
                    
                    st.subheader("Fetching Content:")
                    progress_bar = st.progress(0)
                    st.session_state.content_data = []
                    
                    for i, url in enumerate(st.session_state.sitemap_urls):
                        content = get_jina_reader_content(url)
                        st.session_state.content_data.append({
                            'URL': url,
                            'Full Content': content
                        })
                        progress_bar.progress((i + 1) / len(st.session_state.sitemap_urls))
                    
                    st.subheader("Scraped Content:")
                    content_df = pd.DataFrame(st.session_state.content_data)
                    st.dataframe(content_df)
                else:
                    st.error("No URLs found. Please check the debugging information above for more details.")
            else:
                st.warning('Please enter a website URL')
        
        # Display tables if data exists in session state
        if st.session_state.sitemap_urls:
            st.subheader("Sitemap URLs:")
            sitemap_df = pd.DataFrame({'URL': st.session_state.sitemap_urls})
            st.dataframe(sitemap_df)
        
        if st.session_state.content_data:
            st.subheader("Scraped Content:")
            content_df = pd.DataFrame(st.session_state.content_data)
            st.dataframe(content_df)
        
        # Option to view full content for a selected URL
        if st.session_state.sitemap_urls:
            selected_url = st.selectbox("Select a URL to view full content:", st.session_state.sitemap_urls)
            if selected_url:
                full_content = next((item['Full Content'] for item in st.session_state.content_data if item['URL'] == selected_url), None)
                if full_content:
                    st.text_area(f"Full content for {selected_url}", full_content, height=400)
                else:
                    st.warning("Content not found for the selected URL.")

if __name__ == "__main__":
    main()
