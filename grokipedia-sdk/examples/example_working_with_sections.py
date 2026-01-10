"""Examples for working with article sections"""

from grokipedia_sdk import Client, ArticleNotFound, RequestError
from typing import List, Optional


def example_list_all_sections():
    """List all sections in an article"""
    print("=" * 60)
    print("Example 1: List All Sections")
    print("=" * 60)
    
    with Client() as client:
        try:
            article = client.get_article("Joe_Biden")
            
            print(f"\nArticle: {article.title}")
            print(f"Total sections: {len(article.sections)}\n")
            
            print("Sections:")
            for i, section in enumerate(article.sections, 1):
                indent = "  " * (section.level - 1)
                content_preview = section.content[:80] + "..." if len(section.content) > 80 else section.content
                print(f"{indent}{i}. [Level {section.level}] {section.title}")
                print(f"{indent}   {content_preview}\n")
        
        except (ArticleNotFound, RequestError) as e:
            print(f"Error: {e}")


def example_find_section_by_title():
    """Find a specific section by title (fuzzy matching)"""
    print("\n" + "=" * 60)
    print("Example 2: Find Section by Title")
    print("=" * 60)
    
    with Client() as client:
        article_slug = "Joe_Biden"
        section_titles = [
            "Early Life",
            "Education",
            "Political Career",
            "Presidency"
        ]
        
        try:
            article = client.get_article(article_slug)
            print(f"\nSearching for sections in: {article.title}\n")
            
            for search_title in section_titles:
                # Try exact match first
                section = client.get_section(article_slug, search_title)
                
                if section:
                    print(f"✓ Found: {section.title}")
                    print(f"  Level: {section.level}")
                    print(f"  Content preview: {section.content[:150]}...")
                    print()
                else:
                    # Try finding in sections list
                    found = False
                    for s in article.sections:
                        if search_title.lower() in s.title.lower():
                            print(f"✓ Found similar: {s.title}")
                            print(f"  Level: {s.level}")
                            print(f"  Content preview: {s.content[:150]}...")
                            print()
                            found = True
                            break
                    
                    if not found:
                        print(f"✗ Section '{search_title}' not found\n")
        
        except (ArticleNotFound, RequestError) as e:
            print(f"Error: {e}")


def example_extract_section_hierarchy():
    """Extract and display section hierarchy"""
    print("\n" + "=" * 60)
    print("Example 3: Section Hierarchy")
    print("=" * 60)
    
    with Client() as client:
        try:
            article = client.get_article("Artificial_Intelligence")
            
            print(f"\nArticle: {article.title}")
            print("\nSection Hierarchy:")
            print("-" * 60)
            
            def print_section(section, indent_level=0):
                indent = "  " * indent_level
                marker = "├─" if indent_level > 0 else "└─"
                print(f"{indent}{marker} {section.title} (Level {section.level})")
            
            # Group sections by hierarchy
            current_level = 1
            for section in article.sections:
                if section.level <= current_level:
                    print_section(section, section.level - 1)
                current_level = section.level
            
            print("-" * 60)
            
        except (ArticleNotFound, RequestError) as e:
            print(f"Error: {e}")


def example_get_sections_by_level():
    """Get all sections at a specific heading level"""
    print("\n" + "=" * 60)
    print("Example 4: Sections by Level")
    print("=" * 60)
    
    with Client() as client:
        try:
            article = client.get_article("Joe_Biden")
            
            print(f"\nArticle: {article.title}")
            
            # Group sections by level
            sections_by_level = {}
            for section in article.sections:
                level = section.level
                if level not in sections_by_level:
                    sections_by_level[level] = []
                sections_by_level[level].append(section)
            
            # Display sections by level
            for level in sorted(sections_by_level.keys()):
                sections = sections_by_level[level]
                print(f"\nLevel {level} sections ({len(sections)}):")
                for section in sections:
                    print(f"  - {section.title}")
        
        except (ArticleNotFound, RequestError) as e:
            print(f"Error: {e}")


def example_extract_section_content():
    """Extract and process section content"""
    print("\n" + "=" * 60)
    print("Example 5: Extract Section Content")
    print("=" * 60)
    
    with Client() as client:
        try:
            article = client.get_article("Python_(programming_language)")
            
            print(f"\nArticle: {article.title}")
            print(f"Total sections: {len(article.sections)}\n")
            
            # Find a specific section
            target_section = None
            for section in article.sections:
                if "History" in section.title:
                    target_section = section
                    break
            
            if target_section:
                print(f"Section: {target_section.title}")
                print(f"Level: {target_section.level}")
                print(f"Content length: {len(target_section.content)} characters")
                print(f"Word count: {len(target_section.content.split())} words")
                print(f"\nContent:\n{target_section.content}")
            else:
                print("Section not found")
        
        except (ArticleNotFound, RequestError) as e:
            print(f"Error: {e}")


def example_build_custom_toc():
    """Build a custom table of contents from sections"""
    print("\n" + "=" * 60)
    print("Example 6: Build Custom Table of Contents")
    print("=" * 60)
    
    with Client() as client:
        try:
            article = client.get_article("Artificial_Intelligence")
            
            print(f"\nArticle: {article.title}")
            print("\nDefault TOC:")
            for i, toc_item in enumerate(article.table_of_contents[:10], 1):
                print(f"  {i}. {toc_item}")
            
            # Build custom TOC with word counts
            print("\n\nCustom TOC with Section Info:")
            print("-" * 60)
            
            for section in article.sections[:15]:  # Limit to first 15 for display
                indent = "  " * (section.level - 1)
                word_count = len(section.content.split())
                print(f"{indent}{section.title} ({word_count} words)")
            
            print("-" * 60)
        
        except (ArticleNotFound, RequestError) as e:
            print(f"Error: {e}")


def example_compare_sections():
    """Compare sections across different articles"""
    print("\n" + "=" * 60)
    print("Example 7: Compare Sections Across Articles")
    print("=" * 60)
    
    articles = ["Joe_Biden", "Elon_Musk"]
    section_title = "Early Life"
    
    with Client() as client:
        print(f"\nComparing '{section_title}' sections:\n")
        
        for slug in articles:
            try:
                section = client.get_section(slug, section_title)
                if section:
                    print(f"✓ {slug}:")
                    print(f"  Title: {section.title}")
                    print(f"  Level: {section.level}")
                    print(f"  Word count: {len(section.content.split())}")
                    print(f"  Preview: {section.content[:120]}...")
                    print()
                else:
                    print(f"✗ {slug}: Section '{section_title}' not found\n")
            except Exception as e:
                print(f"✗ {slug}: Error - {e}\n")


def example_navigate_sections():
    """Navigate between sections programmatically"""
    print("\n" + "=" * 60)
    print("Example 8: Navigate Sections")
    print("=" * 60)
    
    with Client() as client:
        try:
            article = client.get_article("Machine_learning")
            
            print(f"\nArticle: {article.title}")
            print(f"Total sections: {len(article.sections)}\n")
            
            # Find a section and get its neighbors
            target_index = None
            for i, section in enumerate(article.sections):
                if "History" in section.title:
                    target_index = i
                    break
            
            if target_index is not None:
                target = article.sections[target_index]
                print(f"Found section: {target.title}")
                
                # Previous section
                if target_index > 0:
                    prev_section = article.sections[target_index - 1]
                    print(f"\nPrevious section: {prev_section.title}")
                
                # Next section
                if target_index < len(article.sections) - 1:
                    next_section = article.sections[target_index + 1]
                    print(f"Next section: {next_section.title}")
                
                # Parent sections (higher level preceding this one)
                print("\nParent sections:")
                for i in range(target_index - 1, -1, -1):
                    s = article.sections[i]
                    if s.level < target.level:
                        print(f"  {s.title} (Level {s.level})")
                        break
            
        except (ArticleNotFound, RequestError) as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    print("\nGrokipedia SDK - Working with Sections Examples")
    print("=" * 60)
    
    try:
        example_list_all_sections()
        example_find_section_by_title()
        example_extract_section_hierarchy()
        example_get_sections_by_level()
        example_extract_section_content()
        example_build_custom_toc()
        example_compare_sections()
        example_navigate_sections()
        
        print("\n" + "=" * 60)
        print("Examples completed!")
        print("=" * 60)
        
    except KeyboardInterrupt:
        print("\n\nExamples interrupted by user.")
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        raise

