"""
Enhanced Web Fetching System for AI Multi-Agent

This module provides robust web content retrieval with multiple fallback strategies,
GitHub API integration, and advanced error handling to address the issues with
accessing repositories and web content.
"""

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time
import random
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
import json
import base64
from bs4 import BeautifulSoup
import re
from urllib.parse import urlparse, urljoin, quote
import os
from ddgs import DDGS
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class WebContent:
    """Structured representation of web content"""
    url: str
    title: str = ""
    content: str = ""
    content_type: str = ""
    success: bool = False
    error_message: str = ""
    source_method: str = ""
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

class EnhancedWebFetcher:
    """Enhanced web fetching system with multiple strategies and robust error handling"""
    
    def __init__(self, github_token: Optional[str] = None):
        self.github_token = github_token or os.getenv('GITHUB_TOKEN')
        self.session = self._create_session()
        
        # User agents for rotation
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Safari/605.1.15'
        ]
    
    def _create_session(self) -> requests.Session:
        """Create a session with retry strategy"""
        session = requests.Session()
        
        # Define retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        return session
    
    def _get_random_user_agent(self) -> str:
        """Get a random user agent"""
        return random.choice(self.user_agents)
    
    def _is_github_url(self, url: str) -> Tuple[bool, Optional[Dict[str, str]]]:
        """Check if URL is a GitHub repository and extract info"""
        github_patterns = [
            r'github\.com/([^/]+)/([^/]+)/?(?:\.git)?$',
            r'github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.+)$',
            r'github\.com/([^/]+)/([^/]+)/tree/([^/]+)/?(.*)$',
            r'github\.com/([^/]+)/([^/]+)/?$'
        ]
        
        for pattern in github_patterns:
            match = re.search(pattern, url)
            if match:
                groups = match.groups()
                repo_info = {
                    'owner': groups[0],
                    'repo': groups[1].replace('.git', ''),
                    'branch': groups[2] if len(groups) > 2 else 'main',
                    'path': groups[3] if len(groups) > 3 else ''
                }
                return True, repo_info
        
        return False, None
    
    def _fetch_github_content(self, repo_info: Dict[str, str], specific_file: str = None) -> WebContent:
        """Fetch content from GitHub using API"""
        owner = repo_info['owner']
        repo = repo_info['repo']
        branch = repo_info.get('branch', 'main')
        path = specific_file or repo_info.get('path', '')
        
        headers = {
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': self._get_random_user_agent()
        }
        
        if self.github_token:
            headers['Authorization'] = f'token {self.github_token}'
        
        try:
            # First, try to get repository info to verify it exists
            repo_url = f'https://api.github.com/repos/{owner}/{repo}'
            logger.info(f"Fetching GitHub repo info: {repo_url}")
            
            repo_response = self.session.get(repo_url, headers=headers, timeout=10)
            
            if repo_response.status_code == 404:
                return WebContent(
                    url=f"https://github.com/{owner}/{repo}",
                    success=False,
                    error_message=f"Repository {owner}/{repo} not found or is private",
                    source_method="github_api"
                )
            
            repo_response.raise_for_status()
            repo_data = repo_response.json()
            
            # If no specific file requested, get README
            if not path or path == '':
                readme_candidates = ['README.md', 'readme.md', 'README.txt', 'readme.txt', 'README']
                
                for readme_file in readme_candidates:
                    content_url = f'https://api.github.com/repos/{owner}/{repo}/contents/{readme_file}'
                    logger.info(f"Trying to fetch README: {content_url}")
                    
                    try:
                        content_response = self.session.get(content_url, headers=headers, timeout=10)
                        if content_response.status_code == 200:
                            content_data = content_response.json()
                            
                            if content_data.get('encoding') == 'base64':
                                content = base64.b64decode(content_data['content']).decode('utf-8')
                                
                                return WebContent(
                                    url=f"https://github.com/{owner}/{repo}",
                                    title=f"{repo} - {repo_data.get('description', 'GitHub Repository')}",
                                    content=f"# {repo}\n\n{repo_data.get('description', '')}\n\n{content}",
                                    content_type="markdown",
                                    success=True,
                                    source_method="github_api",
                                    metadata={
                                        'stars': repo_data.get('stargazers_count', 0),
                                        'forks': repo_data.get('forks_count', 0),
                                        'language': repo_data.get('language', ''),
                                        'updated_at': repo_data.get('updated_at', ''),
                                        'readme_file': readme_file
                                    }
                                )
                    except Exception as e:
                        logger.warning(f"Failed to fetch {readme_file}: {str(e)}")
                        continue
                
                # If no README found, return repo info
                return WebContent(
                    url=f"https://github.com/{owner}/{repo}",
                    title=f"{repo} - {repo_data.get('description', 'GitHub Repository')}",
                    content=f"# {repo}\n\n{repo_data.get('description', 'No description available.')}\n\nRepository found but no README file detected.",
                    content_type="markdown",
                    success=True,
                    source_method="github_api",
                    metadata={
                        'stars': repo_data.get('stargazers_count', 0),
                        'forks': repo_data.get('forks_count', 0),
                        'language': repo_data.get('language', ''),
                        'updated_at': repo_data.get('updated_at', '')
                    }
                )
            
            else:
                # Fetch specific file
                content_url = f'https://api.github.com/repos/{owner}/{repo}/contents/{path}'
                content_response = self.session.get(content_url, headers=headers, timeout=10)
                content_response.raise_for_status()
                
                content_data = content_response.json()
                
                if content_data.get('encoding') == 'base64':
                    content = base64.b64decode(content_data['content']).decode('utf-8')
                    
                    return WebContent(
                        url=f"https://github.com/{owner}/{repo}/blob/{branch}/{path}",
                        title=f"{path} - {repo}",
                        content=content,
                        content_type="file",
                        success=True,
                        source_method="github_api",
                        metadata={'file_path': path, 'repo': repo}
                    )
        
        except requests.exceptions.RequestException as e:
            logger.error(f"GitHub API request failed: {str(e)}")
            return WebContent(
                url=f"https://github.com/{owner}/{repo}",
                success=False,
                error_message=f"GitHub API error: {str(e)}",
                source_method="github_api"
            )
        
        except Exception as e:
            logger.error(f"Unexpected error fetching GitHub content: {str(e)}")
            return WebContent(
                url=f"https://github.com/{owner}/{repo}",
                success=False,
                error_message=f"Unexpected error: {str(e)}",
                source_method="github_api"
            )
    
    def _fetch_with_requests(self, url: str, max_retries: int = 3) -> WebContent:
        """Fetch content using requests with retry logic"""
        for attempt in range(max_retries):
            try:
                headers = {
                    'User-Agent': self._get_random_user_agent(),
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1'
                }
                
                logger.info(f"Fetching URL with requests (attempt {attempt + 1}): {url}")
                
                response = self.session.get(url, headers=headers, timeout=15, allow_redirects=True)
                response.raise_for_status()
                
                # Detect content type
                content_type = response.headers.get('Content-Type', '').lower()
                
                if 'text/html' in content_type or 'text/plain' in content_type:
                    soup = BeautifulSoup(response.content, 'html.parser')
                    
                    # Remove unwanted elements
                    for element in soup(['script', 'style', 'nav', 'footer', 'aside', 'header']):
                        element.decompose()
                    
                    # Extract title
                    title_tag = soup.find('title')
                    title = title_tag.get_text().strip() if title_tag else urlparse(url).netloc
                    
                    # Extract main content
                    # Try to find main content areas
                    main_content = None
                    for selector in ['main', 'article', '.content', '#content', '.main', '#main']:
                        main_content = soup.select_one(selector)
                        if main_content:
                            break
                    
                    if not main_content:
                        main_content = soup.find('body') or soup
                    
                    # Extract text and clean up
                    text = main_content.get_text(separator='\n', strip=True)
                    
                    # Clean up excessive whitespace
                    lines = [line.strip() for line in text.split('\n') if line.strip()]
                    content = '\n'.join(lines)
                    
                    # Limit content size
                    if len(content) > 5000:
                        content = content[:5000] + "\n\n[Content truncated for length...]"
                    
                    return WebContent(
                        url=url,
                        title=title,
                        content=content,
                        content_type="html",
                        success=True,
                        source_method=f"requests_attempt_{attempt + 1}",
                        metadata={'status_code': response.status_code, 'content_length': len(content)}
                    )
                
                else:
                    return WebContent(
                        url=url,
                        title=f"Content from {urlparse(url).netloc}",
                        content=f"Binary content detected (Content-Type: {content_type}). Size: {len(response.content)} bytes",
                        content_type=content_type,
                        success=True,
                        source_method=f"requests_attempt_{attempt + 1}",
                        metadata={'status_code': response.status_code, 'content_type': content_type}
                    )
            
            except requests.exceptions.RequestException as e:
                logger.warning(f"Request attempt {attempt + 1} failed for {url}: {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                    continue
                else:
                    return WebContent(
                        url=url,
                        success=False,
                        error_message=f"All request attempts failed. Last error: {str(e)}",
                        source_method="requests_failed"
                    )
            
            except Exception as e:
                logger.error(f"Unexpected error fetching {url}: {str(e)}")
                return WebContent(
                    url=url,
                    success=False,
                    error_message=f"Unexpected error: {str(e)}",
                    source_method="requests_error"
                )
    
    def search_github_repositories(self, query: str, max_results: int = 5) -> List[WebContent]:
        """Search for GitHub repositories"""
        try:
            headers = {
                'Accept': 'application/vnd.github.v3+json',
                'User-Agent': self._get_random_user_agent()
            }
            
            if self.github_token:
                headers['Authorization'] = f'token {self.github_token}'
            
            # Search repositories
            search_url = f'https://api.github.com/search/repositories'
            params = {
                'q': query,
                'sort': 'stars',
                'order': 'desc',
                'per_page': min(max_results, 10)
            }
            
            logger.info(f"Searching GitHub repositories: {query}")
            
            response = self.session.get(search_url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            results = []
            
            for repo in data.get('items', []):
                content = WebContent(
                    url=repo['html_url'],
                    title=f"{repo['full_name']} - {repo.get('description', '')}",
                    content=f"# {repo['name']}\n\n{repo.get('description', 'No description available.')}\n\nStars: {repo.get('stargazers_count', 0)} | Forks: {repo.get('forks_count', 0)} | Language: {repo.get('language', 'Not specified')}",
                    content_type="repository_info",
                    success=True,
                    source_method="github_search",
                    metadata={
                        'stars': repo.get('stargazers_count', 0),
                        'forks': repo.get('forks_count', 0),
                        'language': repo.get('language', ''),
                        'updated_at': repo.get('updated_at', '')
                    }
                )
                results.append(content)
            
            return results
            
        except Exception as e:
            logger.error(f"GitHub repository search failed: {str(e)}")
            return [WebContent(
                url="",
                success=False,
                error_message=f"GitHub search failed: {str(e)}",
                source_method="github_search_error"
            )]
    
    def enhanced_web_search(self, query: str, max_results: int = 5) -> List[WebContent]:
        """Enhanced web search with content fetching"""
        try:
            results = []
            
            with DDGS() as ddgs:
                logger.info(f"Performing web search: {query}")
                
                for result in ddgs.text(query, max_results=max_results):
                    # Try to fetch actual content from each result
                    web_content = self.fetch_url_content(result['href'])
                    
                    if web_content.success:
                        # Use fetched content
                        web_content.title = result['title']  # Override with search result title
                        results.append(web_content)
                    else:
                        # Fallback to search result snippet
                        results.append(WebContent(
                            url=result['href'],
                            title=result['title'],
                            content=result['body'],
                            content_type="search_snippet",
                            success=True,
                            source_method="ddgs_search",
                            metadata={'search_query': query}
                        ))
            
            return results
            
        except Exception as e:
            logger.error(f"Web search failed: {str(e)}")
            return [WebContent(
                url="",
                success=False,
                error_message=f"Web search failed: {str(e)}",
                source_method="search_error"
            )]
    
    def fetch_url_content(self, url: str) -> WebContent:
        """Main method to fetch content from any URL with multiple strategies"""
        logger.info(f"Fetching content from: {url}")
        
        # Normalize URL
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        # Check if it's a GitHub URL
        is_github, repo_info = self._is_github_url(url)
        
        if is_github and repo_info:
            # Try GitHub API first
            github_result = self._fetch_github_content(repo_info)
            if github_result.success:
                return github_result
            
            # If GitHub API fails, fall back to regular web scraping
            logger.info("GitHub API failed, trying web scraping fallback")
        
        # Try regular web scraping
        return self._fetch_with_requests(url)
    
    def comprehensive_search(self, query: str, include_github: bool = True, max_results: int = 5) -> Dict[str, List[WebContent]]:
        """Perform a comprehensive search using multiple methods"""
        results = {
            'web_search': [],
            'github_repos': [],
            'errors': []
        }
        
        try:
            # Perform web search
            logger.info(f"Starting comprehensive search for: {query}")
            
            web_results = self.enhanced_web_search(query, max_results)
            results['web_search'] = [r for r in web_results if r.success]
            results['errors'].extend([r for r in web_results if not r.success])
            
            # If query suggests it might be GitHub-related, search repositories
            if include_github and any(term in query.lower() for term in ['github', 'repository', 'repo', 'code', 'constitution-of-intelligence']):
                github_results = self.search_github_repositories(query, max_results)
                results['github_repos'] = [r for r in github_results if r.success]
                results['errors'].extend([r for r in github_results if not r.success])
            
            logger.info(f"Search completed. Web: {len(results['web_search'])}, GitHub: {len(results['github_repos'])}, Errors: {len(results['errors'])}")
            
        except Exception as e:
            logger.error(f"Comprehensive search failed: {str(e)}")
            results['errors'].append(WebContent(
                url="",
                success=False,
                error_message=f"Search system error: {str(e)}",
                source_method="comprehensive_search_error"
            ))
        
        return results

# Factory function for easy use
def create_enhanced_fetcher(github_token: Optional[str] = None) -> EnhancedWebFetcher:
    """Create an enhanced web fetcher instance"""
    return EnhancedWebFetcher(github_token=github_token)

# Utility functions for backward compatibility
def robust_fetch_url_content(url: str, github_token: Optional[str] = None) -> str:
    """Fetch URL content with robust error handling - backward compatible"""
    fetcher = create_enhanced_fetcher(github_token)
    result = fetcher.fetch_url_content(url)
    
    if result.success:
        return f"**{result.title}**\n\n{result.content}\n\nSource: {result.url} (via {result.source_method})"
    else:
        return f"Failed to fetch content from {url}: {result.error_message}"

def robust_web_search(query: str, max_results: int = 5, github_token: Optional[str] = None) -> str:
    """Perform robust web search - backward compatible"""
    fetcher = create_enhanced_fetcher(github_token)
    results = fetcher.comprehensive_search(query, include_github=True, max_results=max_results)
    
    output = []
    
    # Web search results
    for result in results['web_search']:
        output.append(f"**{result.title}**\n{result.content}\nSource: {result.url}")
    
    # GitHub repository results
    for result in results['github_repos']:
        output.append(f"**[GitHub Repository] {result.title}**\n{result.content}\nSource: {result.url}")
    
    if not output and results['errors']:
        error_msg = "; ".join([e.error_message for e in results['errors']])
        return f"Search failed: {error_msg}"
    
    return "\n\n".join(output) if output else "No results found."

# Test function
def test_enhanced_fetcher():
    """Test the enhanced fetcher with the problematic repository"""
    fetcher = create_enhanced_fetcher()
    
    # Test the specific repository that was causing issues
    test_urls = [
        "https://github.com/raustinturner/Constitution-of-Intelligence",
        "https://github.com/raustinturner/Constitution-of-Intelligence.git"
    ]
    
    for url in test_urls:
        print(f"\nTesting: {url}")
        result = fetcher.fetch_url_content(url)
        print(f"Success: {result.success}")
        print(f"Method: {result.source_method}")
        if result.success:
            print(f"Title: {result.title}")
            print(f"Content length: {len(result.content)}")
            print(f"Content preview: {result.content[:200]}...")
        else:
            print(f"Error: {result.error_message}")
    
    # Test search
    print(f"\nTesting search for 'Constitution-of-Intelligence raustinturner':")
    search_results = fetcher.comprehensive_search("Constitution-of-Intelligence raustinturner", include_github=True, max_results=3)
    
    for category, results in search_results.items():
        print(f"\n{category.upper()}: {len(results)} results")
        for i, result in enumerate(results):
            print(f"  {i+1}. {result.title} - Success: {result.success}")
            if not result.success:
                print(f"     Error: {result.error_message}")

if __name__ == "__main__":
    test_enhanced_fetcher()
