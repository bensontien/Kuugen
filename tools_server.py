import os
import requests
import aiohttp
import subprocess
from bs4 import BeautifulSoup
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("KuugenTools")

@mcp.tool()
def download_pdf(url: str, filename: str) -> str:
    """
    Download a PDF file from a given URL and save it to the local directory.
    """
    os.makedirs("Papers", exist_ok=True)
    filepath = f"Papers/{filename}.pdf"
    
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        with open(filepath, "wb") as f:
            f.write(response.content)
        return f"Successfully downloaded PDF to {filepath}"
    except Exception as e:
        return f"Failed to download PDF: {str(e)}"

@mcp.tool()
async def fetch_page_content(url: str, max_chars: int = 1000) -> str:
    """
    Asynchronously visit the webpage and scrape plain text content.
    """
    try:
        # Add mock headers to avoid being blocked by target site's anti-bot mechanisms
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        # Set a 10-second timeout to avoid getting stuck on dead websites
        print(f"Testing URL: {url}")
        timeout = aiohttp.ClientTimeout(total=10)
        
        async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
            async with session.get(url) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Remove unnecessary script, style, nav, and footer tags
                    for script in soup(["script", "style", "nav", "footer"]):
                        script.extract()
                        
                    # Get plain text and clean up extra whitespace
                    text = soup.get_text(separator=' ', strip=True)
                    
                    # Limit the maximum character count
                    return text[:max_chars]
                else:
                    return f"(Unable to access webpage, HTTP status code: {response.status})"
    except Exception as e:
        return f"(Webpage read failed: {str(e)})"
    
@mcp.tool()
def execute_windows_command(command: str) -> str:
    """
    Execute a command in the host Windows PowerShell from WSL.
    Use this to check Windows system status, open applications, or read files.
    Example commands: 
    - Open app: 'Start-Process notepad'
    - Check memory: 'Get-CimInstance Win32_OperatingSystem | Select-Object FreePhysicalMemory'
    - List files: 'Get-ChildItem C:\\'
    """
    print(f"[Windows Control] Ready to execute PowerShell command: {command}")

    dangerous_keywords = [
        'remove-item ', 'del ', 'rmdir ', 'stop-computer', 
        'restart-computer', 'stop-process', 'kill '
    ]
    if any(keyword.lower() in command.lower() for keyword in dangerous_keywords):
        return "System Protection: Execution of potentially destructive commands is blocked."

    try:
        result = subprocess.run(
            ["powershell.exe", "-Command", command], 
            capture_output=True, 
            text=True, 
            timeout=15
        )
        
        if result.returncode == 0:
            output = result.stdout.strip()
            if len(output) > 3000:
                output = output[:3000] + "\n...[Output Truncated due to length]"
            return f"Command executed successfully.\nOutput:\n{output}"
        else:
            return f"Command failed.\nError:\n{result.stderr.strip()}"
            
    except subprocess.TimeoutExpired:
        return "Command execution timed out (exceeded 15 seconds)."
    except Exception as e:
        return f"Failed to execute command: {str(e)}"

if __name__ == "__main__":
    # Run the server via standard input/output (the standard MCP communication method)
    mcp.run()
