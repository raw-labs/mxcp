from typing import Dict, Any
from mxcp.auth.context import get_user_context

def whoami() -> Dict[str, Any]:
    """Get current user information from OAuth context without making API calls."""
    context = get_user_context()
    
    try:
        # Extract user information from the OAuth context/profile
        raw_profile = getattr(context, 'raw_profile', {})
        
        # Build user info from available context data
        user_info = {}
        
        # Basic user identifiers
        if 'user_id' in raw_profile:
            user_info['user_id'] = raw_profile['user_id']
        
        if 'organization_id' in raw_profile:
            user_info['organization_id'] = raw_profile['organization_id']
            
        if 'username' in raw_profile:
            user_info['username'] = raw_profile['username']
            
        if 'display_name' in raw_profile:
            user_info['display_name'] = raw_profile['display_name']
            
        if 'email' in raw_profile:
            user_info['email'] = raw_profile['email']
        
        # Instance URL
        urls = raw_profile.get('urls', {})
        if 'custom_domain' in urls:
            user_info['instance_url'] = urls['custom_domain']
        elif 'enterprise' in urls:
            user_info['instance_url'] = urls['enterprise'].replace('/services/Soap/c/{version}', '')
        
        # User preferences
        if 'language' in raw_profile:
            user_info['language'] = raw_profile['language']
            
        if 'locale' in raw_profile:
            user_info['locale'] = raw_profile['locale']
            
        if 'timezone' in raw_profile:
            user_info['timezone'] = raw_profile['timezone']
        
        # If we don't have much from raw_profile, include some basic context info
        if not user_info:
            user_info['access_token_present'] = bool(getattr(context, 'access_token', None))
            user_info['context_type'] = str(type(context).__name__)
        
        return user_info
        
    except AttributeError as e:
        raise Exception(f"Failed to extract user context: {e}") 