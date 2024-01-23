import sys
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
    level=logging.DEBUG,
    stream=sys.stdout
)

PRACTICUM_TOKEN = os.getenv('YA_PR_TOKEN')
TELEGRAM_TOKEN = os.getenv('TG_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TG_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': 'OAuth {}'.format(PRACTICUM_TOKEN)}
LAST_ERROR_MESSAGE = None

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def check_tokens():
    """Проверка доступности переменных окружения."""
    tokens = [PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]
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
        logging.debug('Бот отправил сообщение: {}'.format(message))
    except Exception as error_send_message:
        logging.error(
            'Ошибка при отправке сообщения: {}'.format(error_send_message)
        )


def get_api_answer(timestamp):
    """Запрос к эндпоинту API-сервиса."""
    try:
        response = requests.get(
            ENDPOINT,
            params={'from_date': timestamp},
            headers=HEADERS
        )
        response.raise_for_status()
    except HTTPError as error_request_to_api:
        logging.error(
            'Ошибка при запросе к API. HTTP Status Code: {}. '
            'URL: {}. Параметры: {}. Сообщение: {}'
            .format(
                response.status_code,
                response.url,
                response.request.params,
                error_request_to_api
            )
        )
    except RequestException as error_connection:
        logging.error(
            'Ошибка связи с API при запросе к URL: {} с параметрами: {}. '
            'Сообщение: {}'.format(ENDPOINT, timestamp, error_connection)
        )
    if response.status_code != HTTPStatus.OK:
        if 400 <= response.status_code < 500:
            raise ValueError('Ошибка на стороне клиента.')
        elif 500 <= response.status_code < 600:
            raise ValueError('Ошибка сервера.')
        else:
            raise ValueError('Неизвестный ответ.')
    return response.json()


def check_response(response):
    """Проверка ответа API на соответствие документации."""
    if not isinstance(response, dict):
        raise TypeError('Ответ API не является словарем.')
    if 'homeworks' not in response:
        raise KeyError('Ответ API не содержит ключ "homeworks".')
    if not isinstance(response['homeworks'], list):
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
    global LAST_ERROR_MESSAGE

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
            time.sleep(RETRY_PERIOD)
        except Exception as error_programm:
            logging.error('Сбой в работе программы: {}'.format(error_programm))
            message = 'Сбой в работе программы: {}'.format(error_programm)
            if LAST_ERROR_MESSAGE != message:
                send_message(bot, message)
                LAST_ERROR_MESSAGE = message
            time.sleep(RETRY_PERIOD)
        logging.debug('Конец работы бота.')


if __name__ == '__main__':
    main()
