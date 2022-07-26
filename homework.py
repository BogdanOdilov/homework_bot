import logging
import os
import time
from http import HTTPStatus

import requests
import telegram
from dotenv import load_dotenv

import exceptions

load_dotenv()


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('CHAT_ID')

RETRY_TIME = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    level=logging.INFO,
)

logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
logger.addHandler(handler)


def send_message(bot, message):
    """Отправляет сообщение в чат."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logger.info('Сообщение в чат отправлено')
    except exceptions.SendMessageFailure:
        logger.error('Сбой при отправке сообщения в чат')


def get_api_answer(current_timestamp):
    """Делает запрос к эндпоинту."""
    timestamp = current_timestamp
    params = {'from_date': timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=params)
    except exceptions.APIResponseStatusCodeException:
        logger.error('Сбой при запросе к эндпоинту')
    if response.status_code != HTTPStatus.OK:
        msg = 'Сбой при запросе к эндпоинту'
        logger.error(msg)
        raise exceptions.APIResponseStatusCodeException(msg)
    return response.json()


def check_response(response):
    """Проверяет ответ API на корректность."""
    try:
        homeworks_list = response['homeworks']
    except KeyError as e:
        msg = f'Ошибка доступа по ключу homeworks: {e}'
        logger.error(msg)
        raise exceptions.CheckResponseException(msg)
    if homeworks_list is None:
        msg = 'В ответе API нет словаря с домашками'
        logger.error(msg)
        raise exceptions.CheckResponseException(msg)
    if len(homeworks_list) == 0:
        msg = 'За последнее время нет домашек'
        logger.error(msg)
        raise exceptions.CheckResponseException(msg)
    if not isinstance(homeworks_list, list):
        msg = 'В ответе API домашки представлены не списком'
        logger.error(msg)
        raise exceptions.CheckResponseException(msg)
    return homeworks_list


def parse_status(homework):
    """Извлекает из информации о домашке ее статус."""
    try:
        homework_name = homework.get('homework_name')
    except KeyError as e:
        msg = f'Ошибка доступа по ключу homework_name: {e}'
        logger.error(msg)
    try:
        homework_status = homework.get('status')
    except KeyError as e:
        msg = f'Ошибка доступа по ключу status: {e}'
        logger.error(msg)

    verdict = HOMEWORK_VERDICTS[homework_status]
    if verdict is None:
        msg = 'Неизвестный статус домашки'
        logger.error(msg)
        raise exceptions.UnknownHWStatusException(msg)
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens():
    """Проверяет доступность переменных окружения."""
    return all([TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, PRACTICUM_TOKEN])


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        msg = 'Отсутствует необходимая переменная среды'
        logger.critical(msg)
        raise exceptions.MissingRequiredTokenException(msg)

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time() - 604800)
    previous_status = None
    previous_error = None

    while True:
        try:
            response = get_api_answer(current_timestamp)
        except exceptions.IncorrectAPIResponseException as e:
            if str(e) != previous_error:
                previous_error = str(e)
                send_message(bot, e)
            logger.error(e)
            time.sleep(RETRY_TIME)
            continue
        try:
            homeworks = check_response(response)
            hw_status = homeworks[0].get('status')
            if hw_status != previous_status:
                previous_status = hw_status
                message = parse_status(homeworks[0])
                send_message(bot, message)
            else:
                logger.debug('Обновления статуса нет')

            time.sleep(RETRY_TIME)

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            if previous_error != str(error):
                previous_error = str(error)
                send_message(bot, message)
            logger.error(message)
            time.sleep(RETRY_TIME)


if __name__ == '__main__':
    main()
