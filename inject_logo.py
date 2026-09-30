import os
import re

def update_email_service():
    path = r'c:\Users\Delstaford\Desktop\mmust-dating-ai\mmust-dating-ai\app\email_service.py'
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
    except UnicodeDecodeError:
        with open(path, 'r', encoding='utf-16') as f:
            content = f.read()

    # The user wants to add the logo icon-512.png to the header of all emails.
    # We will search for the main container div that immediately follows the body tag.
    
    def replacer(match):
        full_match = match.group(0)
        
        logo_html = '''
            <!-- LOGO HEADER -->
            <div style="text-align: center; padding: 20px 0; background-color: #ffffff; border-bottom: 1px solid #f0f0f0;">
                <img src="{os.getenv('BASE_URL', 'https://findyourmatch.co.ke')}/static/img/icon-512.png" alt="Find Your Match" style="max-width: 80px; height: auto;">
            </div>'''
            
        return full_match + logo_html
        
    # Match <body ...> followed by whitespace, then <div ... style="max-width... >
    pattern = r'(<body[^>]*>\s*<div[^>]*style="max-width:[^>]*>)'
    
    new_content = re.sub(pattern, replacer, content)
    
    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content)
        
    print("Successfully injected the logo into all email templates!")
        
if __name__ == "__main__":
    update_email_service()
