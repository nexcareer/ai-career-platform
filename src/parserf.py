import requests
import time
import random
import json
import csv
import logging
import re
import html
from datetime import datetime

# ============================================================
# ЛОГИ
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# ============================================================
# КОНФИГУРАЦИЯ
# ============================================================

AREAS = {
    'Казахстан (весь)': 40,
    'Алматы': 159,
    'Астана': 167,
    'Шымкент': 168,
    'Актобе': 162,
    'Атырау': 163,
}

IT_VACANCIES = [
    'Data Analyst',
    'Аналитик данных',
    'Data Scientist',
    'Data Science',
    'Data Engineer',
    'Инженер данных',
    'BI Developer',
    'BI-аналитик',
    'Business Intelligence',
    'Web Analyst',
    'Веб-аналитик',
    'Machine Learning Engineer',
    'ML Engineer',
    'ML-инженер',
    'MLOps',
    'Deep Learning',
    'Computer Vision',
    'NLP Engineer',
    'AI Engineer',
    'Инженер по искусственному интеллекту',
    'Backend Developer',
    'Backend-разработчик',
    'Python Developer',
    'Python-разработчик',
    'Java Developer',
    'Java-разработчик',
    'Golang Developer',
    'Go Developer',
    'Node.js Developer',
    '.NET Developer',
    'C# Developer',
    'PHP Developer',
    'Kotlin Developer',
    'Frontend Developer',
    'Frontend-разработчик',
    'React Developer',
    'iOS Developer',
    'iOS-разработчик',
]

BASE_URL = 'https://api.hh.ru'

HEADERS = {
    'User-Agent': 'KZ-IT-Jobs-Parser/1.0 (Educational project)',
    'HH-User-Agent': 'KZ-IT-Jobs-Parser/1.0 (Educational project)',
}

SEARCH_FIELD = 'name,description'

# Ограничение для ускорения
MAX_VACANCIES_PER_QUERY = 100


# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def clean_html_text(text: str) -> str:
    """Очистка HTML-тегов и HTML-сущностей."""
    if not text:
        return ''
    text = html.unescape(text)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def get_with_retry(url: str, params=None, headers=None, timeout: int = 10, retries: int = 3):
    """GET запрос с повторными попытками."""
    for attempt in range(retries):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=timeout)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            if attempt == retries - 1:
                raise
            wait_time = 2 ** attempt
            logging.warning(f"Повтор запроса через {wait_time} сек. Ошибка: {e}")
            time.sleep(wait_time)


def parse_salary(salary: dict) -> tuple:
    """Вернуть salary_from, salary_to, currency, gross."""
    if salary is None:
        return None, None, None, None
    return (
        salary.get('from'),
        salary.get('to'),
        salary.get('currency'),
        salary.get('gross')
    )


# ============================================================
# API HH
# ============================================================

def get_vacancies_page(query: str, area_id: int, page: int = 0, search_field: str = SEARCH_FIELD) -> dict:
    """
    Получить страницу вакансий из HH API.
    """
    url = f'{BASE_URL}/vacancies'

    params = [
        ('text', query),
        ('area', area_id),
        ('per_page', 100),
        ('page', page),
        ('order_by', 'publication_time'),
    ]

    for field in search_field.split(','):
        params.append(('search_field', field.strip()))

    response = get_with_retry(url, params=params, headers=HEADERS, timeout=15)
    return response.json()


def get_vacancy_detail(vacancy_id: str) -> dict:
    """
    Получить полную информацию по вакансии.
    """
    url = f'{BASE_URL}/vacancies/{vacancy_id}'
    response = get_with_retry(url, headers=HEADERS, timeout=15)
    return response.json()


# ============================================================
# ПАРСИНГ
# ============================================================

def parse_vacancy(item: dict, city_name: str, source_query: str) -> dict:
    """
    Основные поля из search results.
    """
    salary_from, salary_to, currency, salary_gross = parse_salary(item.get('salary'))

    return {
        'id': item.get('id'),
        'source_query': source_query,
        'title': item.get('name'),
        'city': item.get('area', {}).get('name', city_name),
        'company': item.get('employer', {}).get('name'),
        'company_id': item.get('employer', {}).get('id'),
        'experience': item.get('experience', {}).get('name'),
        'employment': item.get('employment', {}).get('name'),
        'schedule': item.get('schedule', {}).get('name'),
        'salary_from': salary_from,
        'salary_to': salary_to,
        'currency': currency,
        'salary_gross': salary_gross,
        'requirement': clean_html_text(item.get('snippet', {}).get('requirement', '')),
        'responsibility': clean_html_text(item.get('snippet', {}).get('responsibility', '')),
        'url': item.get('alternate_url'),
        'published_at': item.get('published_at'),
        'skills': [],
        'description': '',
        'key_skills_text': '',
        'professional_roles': [],
        'employment_form': None,
        'description_html': '',
    }


def enrich_with_details(vacancy: dict) -> dict:
    """
    Добавляет полное описание, навыки и расширенные поля.
    """
    try:
        detail = get_vacancy_detail(vacancy['id'])

        skills = [s.get('name') for s in detail.get('key_skills', []) if s.get('name')]

        vacancy['skills'] = skills
        vacancy['key_skills_text'] = ', '.join(skills)

        vacancy['description_html'] = detail.get('description', '') or ''
        vacancy['description'] = clean_html_text(detail.get('description', '') or '')

        vacancy['employment_form'] = (detail.get('employment_form') or {}).get('name')
        vacancy['professional_roles'] = [
            role.get('name') for role in detail.get('professional_roles', []) if role.get('name')
        ]

        # если в detail есть более точные значения — обновляем
        vacancy['published_at'] = detail.get('published_at', vacancy.get('published_at'))
        vacancy['experience'] = (detail.get('experience') or {}).get('name', vacancy.get('experience'))
        vacancy['employment'] = (detail.get('employment') or {}).get('name', vacancy.get('employment'))
        vacancy['schedule'] = (detail.get('schedule') or {}).get('name', vacancy.get('schedule'))

        # если snippet был пустой, можно попытаться оставить хотя бы часть description
        if not vacancy['requirement'] and vacancy['description']:
            vacancy['requirement'] = vacancy['description'][:500]

        time.sleep(random.uniform(0.4, 1.0))

    except Exception as e:
        logging.warning(f"Не удалось получить детали для вакансии {vacancy['id']}: {e}")

    return vacancy


# ============================================================
# ОСНОВНОЙ СБОРЩИК
# ============================================================

def parse_all_vacancies(
    areas: dict,
    queries: list,
    fetch_details: bool = True,
    search_field: str = SEARCH_FIELD,
    max_vacancies_per_query: int = MAX_VACANCIES_PER_QUERY,
) -> list:
    """
    Собрать вакансии по всем городам и запросам.
    """
    all_vacancies = []
    seen_ids = set()

    for city_name, area_id in areas.items():
        logging.info(f"=== Парсинг города: {city_name} ===")

        for query in queries:
            logging.info(f"  Запрос [{search_field}]: '{query}'")
            page = 0
            collected_for_query = 0

            while True:
                try:
                    data = get_vacancies_page(query, area_id, page, search_field)
                    items = data.get('items', [])

                    if not items:
                        break

                    new_count = 0

                    for item in items:
                        vacancy_id = item.get('id')
                        if vacancy_id in seen_ids:
                            continue

                        seen_ids.add(vacancy_id)
                        new_count += 1
                        collected_for_query += 1

                        vacancy = parse_vacancy(item, city_name, query)

                        if fetch_details:
                            vacancy = enrich_with_details(vacancy)

                        all_vacancies.append(vacancy)

                        if collected_for_query >= max_vacancies_per_query:
                            break

                    total_pages = data.get('pages', 1)
                    logging.info(
                        f"    Стр {page + 1}/{total_pages} | "
                        f"новых: {new_count} | "
                        f"по запросу: {collected_for_query} | "
                        f"всего: {len(all_vacancies)}"
                    )

                    if collected_for_query >= max_vacancies_per_query:
                        break

                    if page >= total_pages - 1:
                        break

                    page += 1
                    time.sleep(random.uniform(0.8, 1.8))

                except requests.HTTPError as e:
                    logging.error(f"HTTP ошибка для '{query}' в {city_name}: {e}")
                    break
                except Exception as e:
                    logging.error(f"Ошибка для '{query}' в {city_name}: {e}")
                    break

    logging.info(f"\n✅ Готово! Уникальных вакансий собрано: {len(all_vacancies)}")
    return all_vacancies


# ============================================================
# СОХРАНЕНИЕ
# ============================================================

def save_to_csv(vacancies: list, filename: str = None) -> str:
    if not vacancies:
        logging.warning("Нет данных для сохранения в CSV.")
        return ''

    if filename is None:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'hh_kz_vacancies_{timestamp}.csv'

    fieldnames = [
        'id',
        'source_query',
        'title',
        'city',
        'company',
        'company_id',
        'experience',
        'employment',
        'employment_form',
        'schedule',
        'salary_from',
        'salary_to',
        'currency',
        'salary_gross',
        'key_skills_text',
        'requirement',
        'responsibility',
        'description',
        'url',
        'published_at',
    ]

    with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for row in vacancies:
            csv_row = row.copy()
            csv_row['professional_roles'] = ', '.join(row.get('professional_roles', []))
            writer.writerow({k: csv_row.get(k) for k in fieldnames})

    logging.info(f"💾 CSV сохранён: {filename}")
    return filename


def save_to_json(vacancies: list, filename: str = None) -> str:
    if filename is None:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'hh_kz_vacancies_{timestamp}.json'

    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(vacancies, f, ensure_ascii=False, indent=2)

    logging.info(f"💾 JSON сохранён: {filename}")
    return filename


# ============================================================
# ЗАПУСК
# ============================================================

if __name__ == '__main__':
    selected_areas = {
        'Алматы': 159,
        'Астана': 167,
        # 'Шымкент': 168,
        # 'Казахстан (весь)': 40,
    }

    selected_queries = [
        'Data Analyst',
        'Python Developer',
        'Business Analyst',
        'Data Engineer',
        'QA Engineer',
    ]

    search_field = 'name,description'
    fetch_details = True

    logging.info("🚀 Запуск парсера hh.kz")
    logging.info(f"Города: {list(selected_areas.keys())}")
    logging.info(f"Запросы: {selected_queries}")
    logging.info(f"search_field='{search_field}'")
    logging.info(f"Полные детали вакансий: {fetch_details}")

    vacancies = parse_all_vacancies(
        areas=selected_areas,
        queries=selected_queries,
        fetch_details=fetch_details,
        search_field=search_field,
        max_vacancies_per_query=100,
    )

    save_to_csv(vacancies)
    save_to_json(vacancies)

    if vacancies:
        v = vacancies[0]
        print("\n=== Пример первой вакансии ===")
        print(f"Название:      {v['title']}")
        print(f"Компания:      {v['company']}")
        print(f"Город:         {v['city']}")
        print(f"Опыт:          {v['experience']}")
        print(f"Занятость:     {v['employment']}")
        print(f"Навыки:        {v['skills']}")
        print(f"Дата:          {v['published_at']}")
        print(f"Ссылка:        {v['url']}")
        print(f"Описание:      {v['description'][:1000]}...")
