import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from urllib.parse import urljoin
import time
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import threading
from bs4 import BeautifulSoup

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
        for line in response.text.split('\n'):
            if line.lower().startswith('sitemap:'):
                return line.split(': ')[1].strip()
    except requests.exceptions.RequestException as e:
        st.warning(f"Failed to fetch robots.txt from {robots_txt_url}: {str(e)}")
    return None

def process_sitemap(content, depth=0):
    if depth > 5:  # Limit recursion depth
        return []
    try:
        root = ET.fromstring(content)
        urls = []
        for sitemap in root.findall('{http://www.sitemaps.org/schemas/sitemap/0.9}sitemap'):
            sitemap_url = sitemap.find('{http://www.sitemaps.org/schemas/sitemap/0.9}loc').text
            urls.extend(get_sitemap_urls(sitemap_url, depth + 1))
        for url in root.findall('{http://www.sitemaps.org/schemas/sitemap/0.9}url'):
            loc = url.find('{http://www.sitemaps.org/schemas/sitemap/0.9}loc').text
            urls.append(loc)
        return urls
    except ET.ParseError as e:
        st.warning(f"Failed to parse sitemap XML: {str(e)}")
        return []

def get_sitemap_urls(url, depth=0):
    if depth > 5:  # Limit recursion depth
        return []
    
    # First, try the standard sitemap location
    sitemap_url = urljoin(url, '/sitemap.xml')
    try:
        response = http.get(sitemap_url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        return process_sitemap(response.content, depth)
    except requests.exceptions.RequestException as e:
        st.warning(f"Failed to fetch sitemap from {sitemap_url}: {str(e)}")

    # If standard location fails, try to find sitemap URL in robots.txt
    sitemap_url = get_sitemap_from_robots_txt(url, depth)
    if sitemap_url:
        try:
            response = http.get(sitemap_url, headers=HEADERS, timeout=10)
            response.raise_for_status()
            return process_sitemap(response.content, depth)
        except requests.exceptions.RequestException as e:
            st.warning(f"Failed to fetch sitemap from {sitemap_url}: {str(e)}")

    # If all else fails, try to scrape links from the homepage
    try:
        response = http.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        return [urljoin(url, a['href']) for a in soup.find_all('a', href=True)]
    except requests.exceptions.RequestException as e:
        st.warning(f"Failed to scrape links from homepage {url}: {str(e)}")
    except ImportError:
        st.warning("BeautifulSoup4 is not installed. Unable to scrape links from homepage.")

    return []

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
                    st.warning("No URLs found. The site might not have a sitemap, or there might be an issue accessing it.")
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
