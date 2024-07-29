import streamlit as st
import requests
import pandas as pd
from urllib.parse import urljoin, urlparse
import time
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import threading
from bs4 import BeautifulSoup

# Initialize session state
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

def extract_links(content, base_url):
    soup = BeautifulSoup(content, 'html.parser')
    links = []
    for a in soup.find_all('a', href=True):
        href = a['href']
        full_url = urljoin(base_url, href)
        if full_url.startswith(base_url):  # Only include internal links
            links.append(full_url)
    return links

@rate_limiter
def get_jina_reader_content(url):
    jina_url = f"https://r.jina.ai/{url}"
    try:
        response = http.get(jina_url, timeout=10)
        response.raise_for_status()
        time.sleep(DELAY_BETWEEN_REQUESTS)  # Ensure 3-second delay between requests
        return response.text
    except requests.exceptions.RequestException as e:
        st.warning(f"Failed to fetch content from {url}: {str(e)}")
        return None

def crawl_website(base_url, max_pages=100):
    crawled_urls = set()
    to_crawl = [base_url]
    content_data = []

    while to_crawl and len(crawled_urls) < max_pages:
        url = to_crawl.pop(0)
        if url in crawled_urls:
            continue
        
        st.info(f"Crawling: {url}")
        page_content = get_jina_reader_content(url)
        
        if page_content:
            crawled_urls.add(url)
            
            # Extract content
            content_data.append({
                'URL': url,
                'Full Content': page_content
            })
            
            # Extract new links
            new_links = extract_links(page_content, base_url)
            for link in new_links:
                if link not in crawled_urls and link not in to_crawl:
                    to_crawl.append(link)
        
        st.success(f"Processed: {url}")

    return content_data

def main():
    st.title('Web Scraper App with Jina Reader')

    if check_password():
        st.success("Logged in successfully!")

        website = st.text_input('Enter website URL (including http:// or https://):')
        
        if st.button('Fetch Website Content'):
            if website:
                with st.spinner('Crawling website and extracting content...'):
                    st.session_state.content_data = crawl_website(website)
                
                if st.session_state.content_data:
                    st.subheader("Scraped Content:")
                    content_df = pd.DataFrame(st.session_state.content_data)
                    st.dataframe(content_df)
                else:
                    st.error("No content found. Please check the debugging information above for more details.")
            else:
                st.warning('Please enter a website URL')
        
        # Display content if it exists in session state
        if st.session_state.content_data:
            st.subheader("Scraped Content:")
            content_df = pd.DataFrame(st.session_state.content_data)
            st.dataframe(content_df)
        
        # Option to view full content for a selected URL
        if st.session_state.content_data:
            urls = [item['URL'] for item in st.session_state.content_data]
            selected_url = st.selectbox("Select a URL to view full content:", urls)
            if selected_url:
                full_content = next((item['Full Content'] for item in st.session_state.content_data if item['URL'] == selected_url), None)
                if full_content:
                    st.text_area(f"Full content for {selected_url}", full_content, height=400)
                else:
                    st.warning("Content not found for the selected URL.")

if __name__ == "__main__":
    main()
