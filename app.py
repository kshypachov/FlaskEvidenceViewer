# from idlelib import query
from flask import Flask, request, render_template, jsonify
#from flask_bootstrap5 import Bootstrap
import xml.etree.ElementTree as ET
import redis
import json
import settings
import logging
import sys


# Зчитування параметрів додатку з конфігураційного файлу
conf = settings.Config('config.ini')

# Налаштування логування
try:
    settings.configure_logging(conf)
    logger = logging.getLogger(__name__)
    logger.info("Логування налаштовано успішно.")
except Exception as e:
    # Якщо виникає помилка при налаштуванні логування, додаток припиняє роботу
    print(f"Помилка налаштування логування: {e}")
    print(f"Програму зупинено!")

logger.debug("Початок ініціалізації додатку")


app = Flask(__name__)
logger = logging.getLogger(__name__)
logger.info("Додаток Flask ініціалізовано.")

@app.template_filter('fromstring')
def fromstring_filter(xml_string):
    """Парсит XML-строку в ElementTree.Element для использования в шаблоне"""
    try:
        return ET.fromstring(xml_string)
    except ET.ParseError as e:
        print(f"Ошибка парсинга XML: {e}")
        return None

def conn_to_redis(redis_host, redis_port, redis_db):
    try:
        redis_client = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5
        )
        # check connection
        redis_client.ping()
        return redis_client
    except redis.ConnectionError as e:
        print(f"Error connecting to Redis: {e}")
        redis_client = None
        return redis_client

def get_data_from_redis(message_uuid, redis_client):
    """Get data from Redis by message_uuid"""
    if redis_client is None:
        print("Redis client is not connected. Aborting.")
        return None

    redis_key = f"oots:message:response:evidence:{message_uuid}"

    print(f"Get data from Redis by id: {redis_key}")

    try:
        # Get dara from Redis
        data = redis_client.get(redis_key)

        if data is None:
            print(f"Key {redis_key} is not found in Redis")
            return None

        print(f"Data got from Redis: {data[:100] if len(data) > 100 else data}...")

        # Parse JSON data if it's JSON'
        try:
            json_data = json.loads(data)
            return json_data
        except json.JSONDecodeError:
            # if not JSON, return as is
            return data

    except redis.RedisError as e:
        print(f"Redis error while getting data: {e}")
        return None
    except Exception as e:
        print(f"Unexpected Redis erro: {e}")
        return None


def parse_xml_to_dict(element):
    """Преобразует XML-элемент в словарь."""
    node = {}
    if element.text and element.text.strip():
        node["__text"] = element.text.strip()
    for child in element:
        if child.tag not in node:
            node[child.tag] = []
        node[child.tag].append(parse_xml_to_dict(child))
    return node


@app.route('/<message_uuid>')
def evidense_previewer(message_uuid):

    # Get returnurl parameter from URL
    returnurl = request.args.get("returnurl")

    # show error if returnurl is not provided
    if not returnurl:
        return render_template("error.html",
                               error_message="Отсутствует обязательный параметр 'returnurl'",
                               error_details="URL должен содержать параметр returnurl. Пример: /?returnurl=https://example.com"), 400
    # show error if message_uuid is not provided
    if not message_uuid:
        return render_template("error.html",
                               error_message="Отсутствует обязательный параметр 'message_uuid'",
                               error_details="URL должен содержать message_uuid. Пример: /3245234089573246345"), 400

    print(message_uuid)
    print(returnurl)

    redis_conn = conn_to_redis(conf.redis_host, conf.redis_port, conf.redis_db)
    data = get_data_from_redis(message_uuid, redis_conn)
    redis_conn.close()

    if data is None:
        return render_template("error.html",
                               error_message="Data not found",
                               error_details=f"Data not found in Redis by id: {message_uuid}"), 404


    if (data["preview"] != True):
        return render_template("error.html",
                               error_message="Data is not previewable",
                               error_details=f"Data is not previewable in Redis by id: {message_uuid}"), 400


    print(data)
    # List for XMLs
    xml_list = []

    for evidence in data["evidences"]:
        xml_list.append({
            "title": evidence["cid"],
            "xml": evidence["content"]
        })

    print(xml_list)

    return render_template("index.html", xml_list=xml_list, message_uuid=message_uuid, returnurl=returnurl)


@app.route('/submit', methods=['POST'])
def submit_approvals():
    """Обрабатывает отправку состояний чекбоксов"""
    data = request.get_json()
    print(data)
    approvals = data.get('approvals', {})

    print("Получены состояния апрувов:")
    for doc_id, is_approved in approvals.items():
        print(f"  Документ {doc_id}: {'Одобрен' if is_approved else 'Не одобрен'}")

    # Здесь можно добавить логику сохранения в базу данных или файл
    redis_conn = conn_to_redis(conf.redis_host, conf.redis_port, conf.redis_db)
    if redis_conn is None:
        return jsonify({"status": "error", "message": "Redis connection failed"}), 500
    json_data = get_data_from_redis(data["message_uuid"], redis_conn)


    print("Получены состояния апрувов:")
    for doc_id, is_approved in approvals.items():

        for evidence in json_data["evidences"]:
            if doc_id == evidence["cid"]:
                evidence["permit"] = is_approved

    json_data["preview"] = False

    redis_conn.set(f"oots:message:response:evidence:{data['message_uuid']}", json.dumps(json_data), 3600)
    redis_conn.set(f"oots:message:request:permit:{data['message_uuid']}", "True", 3600)
    redis_conn.close()

    return jsonify({
        "status": "success",
        "message": "Апрувы успешно сохранены",
        "approvals": approvals
    })


if __name__ == '__main__':
    app.run()