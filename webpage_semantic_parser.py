import json
import logging
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import re
from typing import Dict, List, Optional, Union
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse
import time
from collections import defaultdict
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class ElementSemantics:
    element_type: str
    purpose: str
    context: Dict
    aria_labels: Dict
    is_actionable: bool = True

@dataclass
class PageSection:
    heading: Optional[str]
    purpose: str
    has_interactive_elements: bool
    content: Dict

class WebpageSemanticParser:
    def __init__(self, use_selenium: bool = True, timeout: int = 30):
        self.use_selenium = use_selenium
        self.driver = None
        self.timeout = timeout
        if use_selenium:
            # Initialize headless Chrome driver
            logger.info("Initializing headless Chrome driver")
            options = webdriver.ChromeOptions()
            options.add_argument('--headless')
            options.add_argument('--disable-gpu')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            # Add page load timeout
            self.driver = webdriver.Chrome(options=options)
            self.driver.set_page_load_timeout(self.timeout)
        
        self.actionable_elements = {}
        self.semantic_structure = {}
        self.last_request_time = defaultdict(float)
        self.request_delay = 1.0  # Minimum seconds between requests to same domain
        self.stats = {
            'pages_visited': 0,
            'start_time': None,
            'errors': 0
        }
        
    def __del__(self):
        if self.driver:
            logger.info("Closing Chrome driver")
            self.driver.quit()

    def _respect_rate_limits(self, url: str):
        """Implement rate limiting per domain"""
        domain = urlparse(url).netloc
        elapsed = time.time() - self.last_request_time[domain]
        if elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)
        self.last_request_time[domain] = time.time()

    def extract_all_links(self, soup) -> List[Dict]:
        """Extract all links from the page"""
        links = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            absolute_url = urljoin(self.base_url, href)
            links.append({
                'text': a.get_text(strip=True),
                'href': absolute_url
            })
        return links

    def parse_webpage(self, url: str) -> Dict:
        """Main parsing function to analyze webpage content and structure."""
        self._respect_rate_limits(url)
        logger.info(f"Starting to parse webpage: {url}")
        if self.use_selenium:
            logger.debug("Using Selenium to fetch page content")
            self.driver.get(url)
            # Wait for dynamic content to load
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            page_source = self.driver.page_source
        else:
            # For static pages, use simple HTTP request
            logger.debug("Using requests to fetch static page content")
            import requests
            page_source = requests.get(url).text

        self.soup = BeautifulSoup(page_source, 'html.parser')
        self.base_url = url
        
        # Add this line to extract all links
        all_links = self.extract_all_links(self.soup)
        
        logger.info("Identifying interactive elements")
        self.identify_interactive_elements()
        logger.info("Building semantic hierarchy")
        self.build_semantic_hierarchy()
        
        return {
            'actions': self.get_available_actions(),
            'structure': self.semantic_structure,
            'possible_tasks': self.identify_possible_tasks(),
            'all_links': all_links  # Add this line
        }

    def identify_interactive_elements(self):
        """Identify all interactive elements on the page."""
        logger.debug("Searching for interactive elements")
        # Find all potentially interactive elements
        selectors = [
            'button', 'input', 'a', 'select', 
            '[role="button"]', '[role="link"]', 
            '[role="menuitem"]', 'form'
        ]
        
        for selector in selectors:
            elements = self.soup.select(selector)
            logger.debug(f"Found {len(elements)} elements matching selector: {selector}")
            for element in elements:
                semantics = self.analyze_element(element)
                if semantics.is_actionable:
                    self.actionable_elements[element] = semantics

    def analyze_element(self, element) -> ElementSemantics:
        """Analyze individual element for semantic meaning."""
        element_type = element.name or element.get('role', 'unknown')
        logger.debug(f"Analyzing element of type: {element_type}")
        
        # Gather accessibility information
        aria_labels = {
            'label': element.get('aria-label'),
            'description': element.get('aria-description'),
            'role': element.get('role'),
            'label_text': element.get('label') if element.name == 'input' else None
        }
        
        # Get context and purpose
        context = self.get_element_context(element)
        purpose = self.infer_purpose(element)
        
        return ElementSemantics(
            element_type=element_type,
            purpose=purpose,
            context=context,
            aria_labels=aria_labels
        )

    def infer_purpose(self, element) -> str:
        """Infer the purpose of an element based on various signals."""
        # Get all potential signals
        signals = [
            element.get_text(strip=True),
            element.get('aria-label'),
            element.get('title'),
            element.get('placeholder'),
            element.get('name'),
            element.get('id')
        ]
        
        # Handle class list separately
        class_list = element.get('class', [])
        if class_list:
            signals.append(' '.join(class_list))  # Convert class list to space-separated string
        
        # Filter out None values
        signals = [str(s) for s in signals if s]
        
        action_patterns = {
            'submit': r'submit|send|save|confirm|ok|apply',
            'search': r'search|find|lookup',
            'navigate': r'menu|nav|go to|link',
            'delete': r'delete|remove|clear',
            'edit': r'edit|modify|change|update',
            'form': r'form|input|enter',
            'login': r'login|sign in|signin',
            'register': r'register|sign up|signup',
            'download': r'download|export|get',
            'upload': r'upload|import|attach'
        }
        
        for signal in signals:
            for action, pattern in action_patterns.items():
                if re.search(pattern, signal, re.I):
                    logger.debug(f"Inferred purpose '{action}' from signal: {signal}")
                    return action
        
        logger.debug("Could not infer specific purpose for element")
        return 'unknown'

    def get_element_context(self, element) -> Dict:
        """Get contextual information about where element appears in page."""
        # Find nearest heading
        heading = None
        for parent in element.parents:
            heading_tag = parent.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
            if heading_tag:
                heading = heading_tag.get_text(strip=True)
                break

        # Find parent form and get its name if it exists
        parent_form = element.find_parent('form')
        form_name = parent_form.get('name') if parent_form else None

        return {
            'section_heading': heading,
            'form_name': form_name,
            'in_navigation': bool(element.find_parent('nav')),
            'in_list': bool(element.find_parent(['ul', 'ol'])),
            'url': urljoin(self.base_url, element.get('href', '')) if element.name == 'a' else None
        }

    def build_semantic_hierarchy(self):
        """Build hierarchical structure of page content."""
        logger.info("Building semantic hierarchy of page content")
        self.semantic_structure = {
            'title': self.soup.title.string if self.soup.title else None,
            'main_content': self.parse_main_content(),
            'navigation': self.parse_navigation(),
            'forms': self.parse_forms()
        }

    def parse_main_content(self) -> Dict:
        """Parse main content area of the page."""
        logger.debug("Parsing main content area")
        main = self.soup.find('main') or self.soup.find('body')
        
        return {
            'headings': self.extract_heading_hierarchy(main),
            'sections': self.extract_sections(main)
        }

    def extract_heading_hierarchy(self, container) -> List[Dict]:
        """Extract hierarchical heading structure."""
        headings = container.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
        logger.debug(f"Found {len(headings)} headings")
        hierarchy = []
        
        for heading in headings:
            level = int(heading.name[1])
            hierarchy.append({
                'text': heading.get_text(strip=True),
                'level': level,
                'id': heading.get('id')
            })
            
        return hierarchy

    def extract_sections(self, container) -> List[PageSection]:
        """Extract content sections and their purposes."""
        sections = []
        for section in container.find_all(['section', 'article', 'div']):
            if 'region' in section.get('role', ''):
                heading = section.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
                has_interactive = bool(section.find(['button', 'input', 'a', 'select']))
                
                sections.append(PageSection(
                    heading=heading.get_text(strip=True) if heading else None,
                    purpose=self.infer_section_purpose(section),
                    has_interactive_elements=has_interactive,
                    content=self.extract_section_content(section)
                ))
                
        logger.debug(f"Extracted {len(sections)} content sections")
        return sections

    def infer_section_purpose(self, section) -> str:
        """Infer the purpose of a section based on its content and attributes."""
        signals = [
            section.get('class', []),
            section.get('id', ''),
            section.get('role', ''),
            section.get_text(strip=True)[:100]  # First 100 chars of text
        ]
        
        purpose_patterns = {
            'header': r'header|banner|top',
            'footer': r'footer|bottom',
            'sidebar': r'sidebar|aside',
            'main': r'main|content|article',
            'navigation': r'nav|menu',
            'search': r'search',
            'login': r'login|signin',
            'form': r'form|contact'
        }
        
        for signal in signals:
            if isinstance(signal, list):
                signal = ' '.join(signal)
            for purpose, pattern in purpose_patterns.items():
                if re.search(pattern, str(signal), re.I):
                    logger.debug(f"Inferred section purpose: {purpose}")
                    return purpose
                    
        logger.debug("Could not infer specific section purpose")
        return 'unknown'

    def extract_section_content(self, section) -> Dict:
        """Extract the content structure of a section."""
        return {
            'text_content': section.get_text(strip=True),
            'links': [{'text': a.get_text(strip=True), 
                      'href': urljoin(self.base_url, a.get('href', ''))}
                     for a in section.find_all('a')],
            'images': [{'alt': img.get('alt', ''),
                       'src': urljoin(self.base_url, img.get('src', ''))}
                      for img in section.find_all('img')],
            'forms': self.parse_forms(section)
        }

    def parse_navigation(self) -> List[Dict]:
        """Parse navigation elements of the page."""
        nav_elements = self.soup.find_all(['nav', '[role="navigation"]'])
        logger.debug(f"Found {len(nav_elements)} navigation elements")
        navigation = []
        
        for nav in nav_elements:
            navigation.append({
                'items': [{'text': a.get_text(strip=True),
                          'url': urljoin(self.base_url, a.get('href', ''))}
                         for a in nav.find_all('a')],
                'aria_label': nav.get('aria-label'),
                'location': 'header' if nav.find_parent('header') else 'footer' if nav.find_parent('footer') else 'other'
            })
            
        return navigation

    def parse_forms(self, container=None) -> List[Dict]:
        """Parse forms and their input fields."""
        forms = []
        for form in (container or self.soup).find_all('form'):
            logger.debug(f"Parsing form: {form.get('name', 'unnamed')}")
            form_data = {
                'name': form.get('name'),
                'id': form.get('id'),
                'method': form.get('method', 'get'),
                'action': urljoin(self.base_url, form.get('action', '')),
                'inputs': []
            }
            
            for input_field in form.find_all(['input', 'select', 'textarea']):
                form_data['inputs'].append({
                    'type': input_field.get('type', 'text'),
                    'name': input_field.get('name'),
                    'id': input_field.get('id'),
                    'required': input_field.get('required') is not None,
                    'placeholder': input_field.get('placeholder'),
                    'label': self.find_input_label(input_field)
                })
                
            forms.append(form_data)
            
        return forms

    def find_input_label(self, input_field) -> Optional[str]:
        """Find the label associated with an input field."""
        # Check for aria-label
        aria_label = input_field.get('aria-label')
        if aria_label:
            return aria_label
            
        # Check for associated label tag
        input_id = input_field.get('id')
        if input_id:
            label = self.soup.find('label', {'for': input_id})
            if label:
                return label.get_text(strip=True)
                
        # Check for parent label
        parent_label = input_field.find_parent('label')
        if parent_label:
            # Remove the input's text from the label
            label_text = parent_label.get_text(strip=True)
            input_text = input_field.get_text(strip=True)
            return label_text.replace(input_text, '').strip()
            
        logger.debug(f"No label found for input: {input_field.get('name', 'unnamed')}")
        return None

    def get_available_actions(self) -> Dict:
        """Get all available actions on the page grouped by type."""
        logger.info("Collecting available actions")
        actions = {}
        
        for element, semantics in self.actionable_elements.items():
            if semantics.purpose not in actions:
                actions[semantics.purpose] = []
                
            actions[semantics.purpose].append({
                'element_type': semantics.element_type,
                'context': semantics.context,
                'accessibility': semantics.aria_labels
            })
            
        return actions

    def identify_possible_tasks(self) -> List[Dict]:
        """Identify possible tasks that can be performed on the page."""
        logger.info("Identifying possible tasks")
        tasks = []
        
        # Check form submission tasks
        for form in self.parse_forms():
            tasks.append({
                'type': 'form_submission',
                'name': form.get('name', 'Unknown Form'),
                'requirements': [input_field['name'] for input_field in form['inputs'] if input_field['required']],
                'optional_fields': [input_field['name'] for input_field in form['inputs'] if not input_field['required']]
            })
        
        # Check navigation tasks
        for nav in self.parse_navigation():
            tasks.append({
                'type': 'navigation',
                'available_destinations': [item['text'] for item in nav['items']],
                'location': nav['location']
            })
        
        # Check search capability
        if 'search' in self.get_available_actions():
            tasks.append({
                'type': 'search',
                'requirements': ['query'],
                'location': 'search form or input field'
            })
        
        logger.debug(f"Identified {len(tasks)} possible tasks")
        return tasks

    def traverse_links(self, url: str, depth: int = 3, visited: Optional[set] = None, max_pages: int = 100) -> Dict:
        if visited is None:
            visited = set()
        
        if len(visited) >= max_pages:
            logger.warning(f"Reached maximum page limit of {max_pages}")
            return {}
        
        if depth == 0 or url in visited:
            return {}
        
        logger.info(f"Traversing URL: {url} at depth {depth}")
        visited.add(url)
        
        try:
            page_data = self.parse_webpage(url)
        except Exception as e:
            logger.error(f"Failed to parse page {url}: {e}")
            return {
                'url': url,
                'error': str(e),
                'links': []
            }
        
        index_tree = {
            'url': url,
            'title': page_data['structure'].get('title'),
            'links': []
        }
        
        for link in page_data['all_links']:
            link_url = link['href']
            if link_url not in visited and self._should_follow_link(link_url):
                child_index = self.traverse_links(link_url, depth - 1, visited, max_pages)
                if child_index:
                    index_tree['links'].append(child_index)
        
        return index_tree

    def _should_follow_link(self, url: str) -> bool:
        try:
            parsed = urlparse(url)
            
            # Skip non-HTTP(S) protocols
            if parsed.scheme not in ('http', 'https'):
                return False
                
            # Skip certain file types
            skip_extensions = {'.pdf', '.jpg', '.png', '.gif', '.zip'}
            if any(url.lower().endswith(ext) for ext in skip_extensions):
                return False
                
            # Optional: Stay within same domain
            if parsed.netloc != urlparse(self.base_url).netloc:
                return False
                
            return True
        except Exception as e:
            logger.error(f"Error checking URL {url}: {e}")
            return False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()

    def cleanup(self):
        """Cleanup resources properly"""
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                logger.error(f"Error closing driver: {e}")
            finally:
                self.driver = None

    def _update_stats(self, error: bool = False):
        """Update crawling statistics"""
        self.stats['pages_visited'] += 1
        if error:
            self.stats['errors'] += 1
    
    def get_stats(self) -> Dict:
        """Get crawling statistics"""
        if self.stats['start_time']:
            duration = datetime.now() - self.stats['start_time']
            return {
                **self.stats,
                'duration_seconds': duration.total_seconds()
            }
        return self.stats

# Example usage
def analyze_webpage(url: str) -> Dict:
    logger.info(f"Starting webpage analysis for: {url}")
    parser = WebpageSemanticParser(use_selenium=True)
    understanding = parser.parse_webpage(url)
    
    logger.info("Analysis complete")
    logger.debug("Available actions: %s", understanding['actions'])
    logger.debug("Page structure: %s", understanding['structure'])
    logger.debug("Possible tasks: %s", understanding['possible_tasks'])
    
    return understanding

def analyze_webpage_with_traversal(url: str) -> Dict:
    logger.info(f"Starting webpage analysis with traversal for: {url}")
    parser = WebpageSemanticParser(use_selenium=True)
    index_tree = parser.traverse_links(url)
    
    logger.info("Traversal and analysis complete")
    return index_tree

def main():
    URL = "https://heptabase.com"
    logger.info("Starting main function")
    parser = WebpageSemanticParser()
    understanding = parser.parse_webpage(URL)
    with open('understanding.json', 'w') as f:
        json.dump(understanding, f)
    logger.info("Main function completed")

    logger.info("Starting main function with traversal")
    index_tree = analyze_webpage_with_traversal(URL)
    with open('index_tree.json', 'w') as f:
        json.dump(index_tree, f, indent=2)
    logger.info("Main function with traversal completed")

# To use the parser:
if __name__ == "__main__":
    main()
