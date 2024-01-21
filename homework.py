import logging
import os

import requests
import time
import telegram

from dotenv import load_dotenv
from http import HTTPStatus
from requests.exceptions import HTTPError, RequestException

load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(levelname)s – %(message)s',
    level=logging.DEBUG
)

PRACTICUM_TOKEN = os.getenv('YA_PR_TOKEN')
TELEGRAM_TOKEN = os.getenv('TG_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TG_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}
TIME_POINT = 1705755600
LAST_ERROR_MESSAGE = None


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def check_tokens():
    """Проверка доступности переменных окружения."""
    missing_tokens = []
    if PRACTICUM_TOKEN is None:
        missing_tokens.append('PRACTICUM_TOKEN')
    if TELEGRAM_TOKEN is None:
        missing_tokens.append('TELEGRAM_TOKEN')
    if TELEGRAM_CHAT_ID is None:
        missing_tokens.append('TELEGRAM_CHAT_ID')
    if missing_tokens:
        logging.critical(
            'Отсутствуют переменные окружения: {}'
            .format(', '.join(missing_tokens))
        )
        raise ValueError(
            'Отсутствуют переменные окружения: {}'
            .format(', '.join(missing_tokens))
        )
    return True


def send_message(bot, message):
    """Отправка сообщения в тг-чат."""
    global LAST_ERROR_MESSAGE
    error = False
    try:
        if error and message == LAST_ERROR_MESSAGE:
            logging.info(
                'Повторное сообщение {} не отправлено.'
                .format(message)
            )
            return
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logging.debug('Бот отправил сообщение: {}'.format(message))
        if error:
            LAST_ERROR_MESSAGE = message
    except Exception as e:
        error = True
        logging.error(f'Ошибка при отправке сообщения: {e}')


def get_api_answer(timestamp):
    """Запрос к эндпоинту API-сервиса."""
    try:
        response = requests.get(
            ENDPOINT,
            params={'from_date': timestamp},
            headers=HEADERS
        )
        if response.status_code != HTTPStatus.OK:
            logging.error(
                'Ошибка при запросе к API. Код ответа: {}'
                .format(response.status_code)
            )
            if 400 <= response.status_code < 500:
                raise ValueError('Ошибка на стороне клиента.')
            elif 500 <= response.status_code < 600:
                raise ValueError('Ошибка сервера.')
            else:
                raise ValueError('Неизвестный ответ.')
        return response.json()
    except HTTPError as e:
        logging.error(
            'Ошибка при запросе к API. HTTP Status Code: {}. Сообщение: {}'
            .format(response.status_code, e)
        )
    except RequestException as e:
        logging.error(f'Ошибка связи с API: {e}')


def check_response(response):
    """Проверка ответа API на соответствие документации."""
    if not isinstance(response, dict):
        logging.error('Ответ API не является словарем.')
        raise TypeError('Ответ API не является словарем.')
    if 'homeworks' not in response:
        logging.error('Ответ API не содержит ключ "homeworks".')
        raise KeyError('Ответ API не содержит ключ "homeworks".')
    if not isinstance(response['homeworks'], list):
        logging.error('Данные под ключом "homeworks" не являются списком.')
        raise TypeError('Данные под ключом "homeworks" не являются списком.')
    return response['homeworks']


def parse_status(homework):
    """Получение статуса домашней работы."""
    if 'homework_name' not in homework:
        error_message = 'В ответе API отсутствует ключ "homework_name".'
        logging.error(error_message)
        raise KeyError(error_message)
    homework_name = homework['homework_name']
    status = homework.get('status')
    if status not in HOMEWORK_VERDICTS:
        logging.error('Неизвестный статус домашней работы: {}'.format(status))
        raise ValueError(
            'Неизвестный статус домашней работы: {}'
            .format(status)
        )
    verdict = HOMEWORK_VERDICTS[status]
    return (
        'Изменился статус проверки работы "{}". {}'
        .format(homework_name, verdict)
    )


def main():
    """Основная логика работы бота."""
    check_tokens()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = TIME_POINT
    while True:
        logging.debug('Начало работы бота.')
        try:
            response = get_api_answer(timestamp)
            if response:
                homeworks = check_response(response)
                if homeworks:
                    for homework in homeworks:
                        message = parse_status(homework)
                        if message:
                            send_message(bot, message)
                else:
                    logging.debug('Новых статусов нет.')
                logging.debug('Обновление временной метки timestamp.')
                timestamp = response.get('current_date', timestamp)
                logging.debug('Конец цикла.')
            time.sleep(RETRY_PERIOD)
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            send_message(bot, message)
            time.sleep(RETRY_PERIOD)
        logging.debug('Конец работы бота.')


if __name__ == '__main__':
    main()
