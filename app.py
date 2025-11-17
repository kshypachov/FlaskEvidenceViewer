from flask import Flask, request, render_template, jsonify
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
    """Розбирає XML-рядок у ElementTree.Element для використання в шаблоні"""
    try:
        return ET.fromstring(xml_string)
    except ET.ParseError as e:
        print(f"Помилка парсингу XML: {e}")
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
        # перевірка з'єднання
        redis_client.ping()
        return redis_client
    except redis.ConnectionError as e:
        print(f"Error connecting to Redis: {e}")
        redis_client = None
        return redis_client

def get_data_from_redis(message_uuid, redis_client):
    """Отримати дані з Redis за message_uuid"""
    if redis_client is None:
        print("Redis client is not connected. Aborting.")
        return None

    redis_key = f"oots:message:response:evidence:{message_uuid}"

    print(f"Get data from Redis by id: {redis_key}")

    try:
        # Отримати дані з Redis
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
            # якщо не JSON, повернути як є
            return data

    except redis.RedisError as e:
        print(f"Redis error while getting data: {e}")
        return None
    except Exception as e:
        print(f"Unexpected Redis erro: {e}")
        return None


def parse_xml_to_dict(element):
    """Перетворює XML-елемент у словник."""
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

    # Отримати параметр returnurl з URL
    returnurl = request.args.get("returnurl")

    # показати помилку, якщо returnurl не вказано
    if not returnurl:
        return render_template("error.html",
                               error_message="Missing required parameter 'returnurl'",
                               error_details="URL must include the returnurl parameter. Example: /?returnurl=https://example.com"), 400
    # показати помилку, якщо message_uuid не вказано
    if not message_uuid:
        return render_template("error.html",
                               error_message="Missing required parameter 'message_uuid'",
                               error_details="URL must contain message_uuid. Example: /3245234089573246345"), 400

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
    # Список для XML
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
    """Опрацьовує відправку станів чекбоксів"""
    data = request.get_json()
    print(data)
    approvals = data.get('approvals', {})

    print("Received approval states:")
    for doc_id, is_approved in approvals.items():
        print(f"  Document {doc_id}: {'Approved' if is_approved else 'Not approved'}")

    # Тут можна додати логіку збереження в базу даних або файл
    redis_conn = conn_to_redis(conf.redis_host, conf.redis_port, conf.redis_db)
    if redis_conn is None:
        return jsonify({"status": "error", "message": "Redis connection failed"}), 500
    json_data = get_data_from_redis(data["message_uuid"], redis_conn)


    print("Received approval states:")
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
        "message": "Approvals saved successfully",
        "approvals": approvals
    })


if __name__ == '__main__':
    app.run()