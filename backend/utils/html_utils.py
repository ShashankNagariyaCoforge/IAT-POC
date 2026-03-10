import re
from bs4 import BeautifulSoup

def clean_html(html_content: str) -> str:
    """
    Strips HTML tags and CSS from a string.
    If the content looks like HTML, it uses BeautifulSoup to get text.
    Otherwise, it returns the content as-is.
    """
    if not html_content:
        return ""
        
    # Quick check if it contains any tags
    if "<" not in html_content or ">" not in html_content:
        return html_content
        
    try:
        soup = BeautifulSoup(html_content, "lxml")
        
        # Remove scripts and styles
        for script_or_style in soup(["script", "style"]):
            script_or_style.decompose()
            
        # Get text
        text = soup.get_text(separator="\n")
        
        # Clean up whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = "\n".join(chunk for chunk in chunks if chunk)
        
        return text
    except Exception:
        # Fallback to crude regex if BeautifulSoup fails
        clean = re.sub(r'<[^>]+>', '', html_content)
        return clean.strip()
