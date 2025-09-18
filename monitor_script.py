import os
import io
import requests
import pdfplumber
import difflib
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import anthropic

def download_and_extract_pdf(url):
    """Download PDF and extract text content"""
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        text_content = ""
        with pdfplumber.open(io.BytesIO(response.content)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_content += page_text + "\n"
        
        return text_content.strip()
    except Exception as e:
        raise Exception(f"Failed to download/extract PDF: {str(e)}")

def load_previous_content():
    """Load previous week's content from file"""
    try:
        with open('previous_content.txt', 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return ""

def save_current_content(content):
    """Save current content for next week's comparison"""
    with open('previous_content.txt', 'w', encoding='utf-8') as f:
        f.write(content)

def detect_changes(old_content, new_content):
    """Detect changes between two text versions"""
    if not old_content:
        return "First run - no previous content to compare", new_content
    
    if old_content.strip() == new_content.strip():
        return "No changes detected", ""
    
    # Generate diff
    diff = list(difflib.unified_diff(
        old_content.splitlines(keepends=True),
        new_content.splitlines(keepends=True),
        fromfile='Previous Week',
        tofile='Current Week',
        lineterm=''
    ))
    
    diff_text = ''.join(diff)
    return "Changes detected", diff_text

def analyze_changes_with_claude(diff_text, new_content):
    """Use Claude to analyze and summarize changes"""
    client = anthropic.Anthropic(api_key=os.environ['CLAUDE_API_KEY'])
    
    if not diff_text or diff_text == "":
        return "No changes to analyze."
    
    prompt = f"""Please analyze the changes in this document and provide a clear, concise summary.
    
Focus on:
- What sections changed
- Key additions or deletions
- Important updates or modifications
- Overall significance of changes

Here are the detected changes:
{diff_text[:8000]}  # Limit to avoid token limits

Please provide a professional summary suitable for an email."""

    try:
        message = client.messages.create(
            model="claude-3-sonnet-20240229",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text
    except Exception as e:
        return f"Error analyzing changes with Claude: {str(e)}\n\nRaw diff:\n{diff_text[:2000]}"

def send_email(subject, body):
    """Send email notification"""
    sender_email = os.environ['SENDER_EMAIL']
    sender_password = os.environ['SENDER_PASSWORD'] 
    recipient_email = os.environ['RECIPIENT_EMAIL']
    
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = recipient_email
    msg['Subject'] = subject
    
    msg.attach(MIMEText(body, 'plain'))
    
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        text = msg.as_string()
        server.sendmail(sender_email, recipient_email, text)
        server.quit()
        print("Email sent successfully!")
    except Exception as e:
        print(f"Failed to send email: {str(e)}")

def main():
    pdf_url = os.environ['PDF_URL']
    
    try:
        print("Starting PDF monitoring...")
        
        # Download and extract current content
        print("Downloading and extracting PDF...")
        current_content = download_and_extract_pdf(pdf_url)
        
        # Load previous content
        print("Loading previous content...")
        previous_content = load_previous_content()
        
        # Detect changes
        print("Detecting changes...")
        change_status, diff_text = detect_changes(previous_content, current_content)
        
        # Prepare email content
        if change_status == "No changes detected":
            subject = "PDF Monitor: No Changes This Week"
            body = f"""Weekly PDF Monitoring Report - {datetime.now().strftime('%Y-%m-%d')}

No changes detected in the monitored PDF since last week.

Document URL: {pdf_url}
Status: Up to date
"""
        else:
            print("Analyzing changes with Claude...")
            analysis = analyze_changes_with_claude(diff_text, current_content)
            
            subject = "PDF Monitor: Changes Detected"
            body = f"""Weekly PDF Monitoring Report - {datetime.now().strftime('%Y-%m-%d')}

Changes have been detected in the monitored PDF!

SUMMARY:
{analysis}

Document URL: {pdf_url}
Status: Updated

---
This is an automated report from your PDF monitoring system.
"""
        
        # Send email notification
        print("Sending email notification...")
        send_email(subject, body)
        
        # Save current content for next comparison
        save_current_content(current_content)
        print("Content saved for next week's comparison.")
        
    except Exception as e:
        error_subject = "PDF Monitor: Error Occurred"
        error_body = f"""PDF Monitoring Error - {datetime.now().strftime('%Y-%m-%d')}

An error occurred while monitoring the PDF:

Error: {str(e)}

Document URL: {pdf_url}

Please check the GitHub Actions logs for more details.
"""
        send_email(error_subject, error_body)
        raise

if __name__ == "__main__":
    main()