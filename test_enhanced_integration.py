#!/usr/bin/env python3
"""
Test script to verify the enhanced web fetcher integration works with the main app
"""

import sys
import os
sys.path.append('.')

from enhanced_web_fetcher import create_enhanced_fetcher

def test_github_repository_access():
    """Test accessing the specific repository that was problematic"""
    print("🧪 Testing Enhanced Web Fetcher Integration")
    print("=" * 50)
    
    fetcher = create_enhanced_fetcher()
    
    # Test the problematic repository
    test_urls = [
        "https://github.com/raustinturner/Constitution-of-Intelligence",
        "https://github.com/raustinturner/Constitution-of-Intelligence.git"
    ]
    
    for url in test_urls:
        print(f"\n📖 Testing: {url}")
        result = fetcher.fetch_url_content(url)
        
        if result.success:
            print(f"✅ SUCCESS!")
            print(f"   Title: {result.title[:80]}...")
            print(f"   Method: {result.source_method}")
            print(f"   Content Length: {len(result.content):,} characters")
            print(f"   Content Preview:")
            print(f"   {result.content[:200]}...")
            
            # Check for key content
            if "Constitution of Intelligence" in result.content:
                print("✅ Key content found: 'Constitution of Intelligence'")
            else:
                print("⚠️  Key content not found")
                
        else:
            print(f"❌ FAILED: {result.error_message}")
    
    # Test comprehensive search
    print(f"\n🔍 Testing comprehensive search for 'Constitution-of-Intelligence':")
    search_results = fetcher.comprehensive_search(
        "Constitution-of-Intelligence raustinturner", 
        include_github=True, 
        max_results=3
    )
    
    print(f"   Web Results: {len(search_results['web_search'])}")
    print(f"   GitHub Results: {len(search_results['github_repos'])}")
    print(f"   Errors: {len(search_results['errors'])}")
    
    if search_results['github_repos']:
        print("✅ GitHub repository search working")
        for repo in search_results['github_repos'][:1]:  # Show first result
            print(f"   Found: {repo.title[:60]}...")
    
    # Test backwards compatibility functions
    print(f"\n🔄 Testing backward compatibility functions...")
    
    from enhanced_web_fetcher import robust_fetch_url_content, robust_web_search
    
    # Test robust_fetch_url_content
    content = robust_fetch_url_content("https://github.com/raustinturner/Constitution-of-Intelligence")
    if "Constitution of Intelligence" in content:
        print("✅ robust_fetch_url_content working")
    else:
        print("❌ robust_fetch_url_content failed")
    
    # Test robust_web_search  
    search_content = robust_web_search("Constitution-of-Intelligence", max_results=2)
    if len(search_content) > 100:  # Should have meaningful content
        print("✅ robust_web_search working")
    else:
        print("❌ robust_web_search failed")
    
    print("\n" + "=" * 50)
    print("🎉 Enhanced Web Fetcher Integration Test Complete!")
    print("💡 The issues with accessing GitHub repositories should now be resolved.")

if __name__ == "__main__":
    test_github_repository_access()
