import sys
import logging
import os

import requests
import time
import telegram

from dotenv import load_dotenv
from http import HTTPStatus
from requests.exceptions import RequestException
from telegram.error import TelegramError

from exceptions import SendMessageError

load_dotenv()

logger = logging.getLogger('hw_bot_logger')
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(levelname)s – %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

PRACTICUM_TOKEN = os.getenv('YA_PR_TOKEN')
TELEGRAM_TOKEN = os.getenv('TG_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TG_CHAT_ID')

RETRY_PERIOD = 600
CYCLE_UPDATE_TIME_IN_SECONDS = RETRY_PERIOD
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': 'OAuth {}'.format(PRACTICUM_TOKEN)}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def check_tokens():
    """Проверка доступности переменных окружения."""
    tokens = (PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)
    missing_tokens = []
    for token in tokens:
        if token is None:
            missing_tokens.append(str(token))
    if not missing_tokens:
        logging.info('Переменные окружения определены.')
        return True
    error_message = (
        'Отсутствуют переменные окружения: {}'
        .format(', '.join(missing_tokens))
    )
    logging.critical(error_message)
    sys.exit(error_message)


def send_message(bot, message):
    """Отправка сообщения в тг-чат."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except TelegramError:
        raise SendMessageError('Ошибка отправки сообщения в Telegram')
    logging.debug('Бот отправил сообщение: {}'.format(message))


def get_api_answer(timestamp):
    """Запрос к эндпоинту API-сервиса."""
    try:
        response = requests.get(
            ENDPOINT,
            params={'from_date': timestamp},
            headers=HEADERS
        )
    except RequestException as error_connection:
        raise error_connection(
            'Ошибка связи с API при запросе к URL: {} с параметрами: {}. '
            'Сообщение: {}'.format(ENDPOINT, timestamp, error_connection)
        )
    if response.status_code != HTTPStatus.OK:
        raise ValueError(
            'Ошибка при запросе к API. HTTP Status Code: {}. '
            'URL: {}. Параметры: {}.'.format(
                response.status_code,
                response.url,
                response.request.params
            )
        )
    return response.json()


def check_response(response):
    """Проверка ответа API на соответствие документации."""
    key_from_api = response['homeworks'] if 'homeworks' in response else None
    if not isinstance(response, dict):
        raise TypeError('Ответ API не является словарем.')
    if 'homeworks' not in response:
        raise KeyError('Ответ API не содержит ключ "homeworks".')
    if not isinstance(key_from_api, list):
        raise TypeError('Данные под ключом "homeworks" не являются списком.')
    return key_from_api


def parse_status(homework):
    """Получение статуса домашней работы."""
    if 'homework_name' not in homework:
        raise KeyError('В ответе API отсутствует ключ "homework_name".')
    homework_name = homework['homework_name']
    status = homework.get('status')
    if status not in HOMEWORK_VERDICTS:
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
    timestamp = int(time.time())
    last_error_message = None

    while True:
        logging.debug('Начало работы бота.')
        try:
            api_data = get_api_answer(timestamp)
            if api_data:
                homeworks = check_response(api_data)
                if not homeworks:
                    logging.debug('Новых статусов нет.')
                for homework in homeworks:
                    message = parse_status(homework)
                    if message:
                        send_message(bot, message)
                logging.debug('Обновление временной метки timestamp.')
                timestamp = api_data.get('current_date', int(time.time()))
                logging.debug('Конец цикла.')
            time.sleep(CYCLE_UPDATE_TIME_IN_SECONDS)
        except Exception as error_programm:
            logging.exception(
                'Сбой в работе программы: {}'.format(error_programm)
            )
            message = 'Сбой в работе программы: {}'.format(error_programm)
            if last_error_message != message:
                last_error_message = message
            time.sleep(CYCLE_UPDATE_TIME_IN_SECONDS)
        logging.debug('Конец итерации.')


if __name__ == '__main__':
    main()
