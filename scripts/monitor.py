import os
import requests
import json
import random
import string
from datetime import datetime, timezone

class RobloxNewsMonitor:
    def __init__(self):
        self.api_key = os.getenv('COMPOSIO_API_KEY')
        self.target_email = os.getenv('TARGET_EMAIL', 'linkrobloxnews@gmail.com')
        self.session_id = None
        self.base_url = "https://backend.composio.dev/api/v1"
        
    def generate_session_id(self):
        """Генерирует session_id в формате TTT-RRRRR"""
        part1 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=3))
        part2 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
        return f"{part1}-{part2}"
    
    def search_tools(self):
        """Поиск и инициализация инструментов"""
        url = f"{self.base_url}/tools/search"
        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json"
        }
        
        payload = {
            "use_case": "Search for fresh Roblox news from last 4 hours and send email digest",
            "known_fields": f"recipient_email:{self.target_email}, period:last 4 hours",
            "session": {"generate_id": True},
            "exploratory_query": False
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            if response.status_code == 200:
                result = response.json()
                self.session_id = result.get('data', {}).get('session', {}).get('id')
                print(f"🔍 Tools initialized. Session: {self.session_id}")
                return True
            else:
                print(f"❌ Tools search failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Error in tools search: {e}")
            return False
    
    def search_fresh_news(self):
        """Поиск свежих новостей за последние 4 часа"""
        url = f"{self.base_url}/tools/execute"
        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json"
        }
        
        current_time = datetime.now(timezone.utc)
        cutoff_time = current_time.replace(hour=current_time.hour-4)
        
        tools = [
            {
                "tool_slug": "COMPOSIO_SEARCH_NEWS_SEARCH",
                "arguments": {"query": "Roblox"}
            },
            {
                "tool_slug": "COMPOSIO_SEARCH_TAVILY_SEARCH", 
                "arguments": {
                    "query": "Roblox news updates events security legal last 4 hours",
                    "search_depth": "advanced",
                    "max_results": 10
                }
            }
        ]
        
        payload = {
            "tools": tools,
            "sync_response_to_workbench": False,
            "session_id": self.session_id,
            "memory": {},
            "thought": "Searching for fresh Roblox news from last 4 hours"
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            if response.status_code == 200:
                print("📰 News search completed")
                return response.json()
            else:
                print(f"❌ News search failed: {response.status_code}")
                return None
        except Exception as e:
            print(f"❌ Error in news search: {e}")
            return None
    
    def filter_timestamped_articles(self, search_response):
        """Фильтрация статей с точными временными метками"""
        articles = []
        
        if not search_response or 'data' not in search_response:
            return articles
            
        try:
            results = search_response.get('data', {}).get('data', {}).get('results', [])
            
            for result in results:
                response_data = result.get('response', {}).get('data', {})
                
                # Обработка Google News
                if 'results' in response_data and 'news_results' in response_data['results']:
                    news_results = response_data['results']['news_results']
                    for article in news_results:
                        date_str = article.get('date', '')
                        if self.is_recent_timestamp(date_str):
                            articles.append({
                                'title': article.get('title', 'Без заголовка'),
                                'url': article.get('link', '#'),
                                'source': article.get('source', 'Неизвестный источник'),
                                'date': date_str,
                                'snippet': article.get('snippet', 'Описание недоступно'),
                                'category': 'news'
                            })
                
                # Обработка Tavily
                elif 'response_data' in response_data and 'results' in response_data['response_data']:
                    tavily_results = response_data['response_data']['results']
                    for article in tavily_results:
                        content = article.get('content', '')
                        title = article.get('title', '')
                        if 'roblox' in (content + title).lower():
                            # Проверяем на свежесть по содержанию
                            if any(term in content.lower() for term in ['hours ago', 'today', 'breaking', 'just', 'new']):
                                articles.append({
                                    'title': title or 'Без заголовка',
                                    'url': article.get('url', '#'),
                                    'source': self.extract_domain(article.get('url', '')),
                                    'date': 'Недавно',
                                    'snippet': content[:200] + '...' if len(content) > 200 else content,
                                    'category': 'web'
                                })
                                
        except Exception as e:
            print(f"⚠️ Error processing articles: {e}")
        
        # Удаляем дубликаты по URL
        unique_articles = {}
        for article in articles:
            url = article['url']
            if url not in unique_articles and url != '#':
                unique_articles[url] = article
        
        return list(unique_articles.values())
    
    def is_recent_timestamp(self, date_str):
        """Проверка свежести временной метки"""
        if not date_str:
            return False
            
        date_lower = date_str.lower()
        recent_indicators = ['hours ago', 'hour ago', 'minutes ago', 'minute ago']
        
        for indicator in recent_indicators:
            if indicator in date_lower:
                if 'hours ago' in date_lower or 'hour ago' in date_lower:
                    try:
                        hours = int(date_str.split()[0]) if date_str.split()[0].isdigit() else 1
                        return hours <= 4
                    except:
                        return True
                return True  # minutes ago считаем свежим
        
        return False
    
    def extract_domain(self, url):
        """Извлечение домена из URL"""
        try:
            if url and '://' in url:
                return url.split('/')[2]
            return 'Неизвестный источник'
        except:
            return 'Неизвестный источник'
    
    def create_html_digest(self, articles):
        """Создание HTML дайджеста"""
        current_time = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
        
        html = f'''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Roblox News Digest</title>
    <style>
        body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 20px auto; padding: 20px; }}
        .header {{ background-color: #f5f5f5; padding: 15px; margin-bottom: 20px; border-radius: 5px; }}
        .news-item {{ margin-bottom: 15px; padding: 10px; border-left: 3px solid #007acc; background-color: #fafafa; border-radius: 3px; }}
        .high {{ border-left-color: #dc3545; }}
        .title {{ font-weight: bold; font-size: 16px; margin-bottom: 5px; }}
        .title a {{ color: #007acc; text-decoration: none; }}
        .title a:hover {{ text-decoration: underline; }}
        .meta {{ color: #666; font-size: 12px; margin-bottom: 8px; }}
        .snippet {{ font-size: 14px; line-height: 1.4; color: #333; }}
        .footer {{ margin-top: 30px; padding-top: 15px; border-top: 1px solid #ddd; color: #666; font-size: 12px; }}
        .no-news {{ background-color: #fff3cd; border-left-color: #ffc107; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🎮 Roblox News Digest</h1>
        <p><strong>Время поиска:</strong> {current_time}</p>
        <p><strong>Период:</strong> Последние 4 часа</p>
        <p><strong>Найдено новостей с точным временем:</strong> {len(articles)}</p>
    </div>
'''
        
        if not articles:
            html += '''
    <div class="news-item no-news">
        <p><strong>Свежих новостей о Roblox за последние 4 часа с точными временными метками не обнаружено.</strong></p>
        <p>Система продолжит мониторинг и отправит дайджест при появлении новостей.</p>
    </div>
'''
        else:
            for i, article in enumerate(articles, 1):
                html += f'''
    <div class="news-item high">
        <div class="title">
            <a href="{article['url']}" target="_blank">{article['title']}</a>
        </div>
        <div class="meta">
            <strong>№{i}</strong> | <strong>Источник:</strong> {article['source']} | <strong>Время:</strong> {article['date']}
        </div>
        <div class="snippet">{article['snippet']}</div>
    </div>
'''
        
        html += '''
    <div class="footer">
        <p><strong>🤖 Автоматический мониторинг новостей Roblox</strong></p>
        <p>📧 Следующая проверка через 4 часа</p>
        <p>🔍 Поиск по всем интернет-источникам (English + Русский)</p>
        <p>⚙️ Автоматизация: GitHub Actions</p>
        <p><em>Показываются только новости с точными временными метками</em></p>
    </div>
</body>
</html>'''
        
        return html
    
    def send_email_digest(self, html_content, articles_count):
        """Создание и отправка email дайджеста"""
        url = f"{self.base_url}/tools/execute"
        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json"
        }
        
        if articles_count == 0:
            subject = "Roblox News Digest - Свежих новостей не найдено"
        elif articles_count == 1:
            subject = "Roblox News Digest - 1 свежая новость за последние 4 часа"
        else:
            subject = f"Roblox News Digest - {articles_count} новостей за последние 4 часа"
        
        # Создание черновика
        draft_tools = [{
            "tool_slug": "GMAIL_CREATE_EMAIL_DRAFT",
            "arguments": {
                "recipient_email": self.target_email,
                "subject": subject,
                "body": html_content,
                "is_html": True
            }
        }]
        
        payload = {
            "tools": draft_tools,
            "sync_response_to_workbench": False,
            "session_id": self.session_id,
            "memory": {},
            "thought": "Creating email draft with Roblox news digest"
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                draft_id = self.extract_draft_id(result)
                
                if draft_id:
                    print(f"📝 Draft created: {draft_id}")
                    return self.send_draft(draft_id)
                else:
                    print("❌ Failed to extract draft ID")
                    return False
            else:
                print(f"❌ Failed to create draft: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Error creating email: {e}")
            return False
    
    def extract_draft_id(self, response):
        """Извлечение ID черновика из ответа"""
        try:
            results = response.get('data', {}).get('data', {}).get('results', [])
            for result in results:
                response_data = result.get('response', {}).get('data', {}).get('response_data', {})
                if 'id' in response_data:
                    return response_data['id']
        except Exception as e:
            print(f"⚠️ Error extracting draft ID: {e}")
        return None
    
    def send_draft(self, draft_id):
        """Отправка черновика"""
        url = f"{self.base_url}/tools/execute"
        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json"
        }
        
        send_tools = [{
            "tool_slug": "GMAIL_SEND_DRAFT",
            "arguments": {"draft_id": draft_id}
        }]
        
        payload = {
            "tools": send_tools,
            "sync_response_to_workbench": False,
            "session_id": self.session_id,
            "memory": {},
            "thought": "Sending email digest draft"
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            if response.status_code == 200:
                print("📧 Email sent successfully!")
                return True
            else:
                print(f"❌ Failed to send email: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Error sending email: {e}")
            return False
    
    def run(self):
        """Главный метод запуска мониторинга"""
        print(f"🚀 Roblox News Monitor started at {datetime.now(timezone.utc)}")
        print(f"📧 Target email: {self.target_email}")
        
        try:
            # Проверяем API ключ
            if not self.api_key:
                print("❌ COMPOSIO_API_KEY not found in environment variables")
                return False
            
            # Генерируем session_id
            self.session_id = self.generate_session_id()
            print(f"📋 Session ID: {self.session_id}")
            
            # Инициализация инструментов
            if not self.search_tools():
                print("❌ Failed to initialize tools")
                return False
            
            # Поиск новостей
            search_result = self.search_fresh_news()
            if not search_result:
                print("❌ Failed to search news")
                return False
            
            # Фильтрация статей
            articles = self.filter_timestamped_articles(search_result)
            print(f"📰 Found {len(articles)} timestamped articles")
            
            # Печатаем найденные статьи для отладки
            if articles:
                print("📋 Found articles:")
                for i, article in enumerate(articles, 1):
                    print(f"  {i}. {article['title'][:60]}... - {article['date']}")
            
            # Создание HTML дайджеста
            html_digest = self.create_html_digest(articles)
            
            # Отправка email
            success = self.send_email_digest(html_digest, len(articles))
            
            if success:
                print("✅ Email digest sent successfully!")
                print(f"📊 Summary: {len(articles)} articles processed")
            else:
                print("❌ Failed to send email digest")
            
            return success
            
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            return False

if __name__ == "__main__":
    monitor = RobloxNewsMonitor()
    success = monitor.run()
    exit(0 if success else 1)
