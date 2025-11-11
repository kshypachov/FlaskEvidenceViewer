
import configparser
import logging
import os

logger = logging.getLogger(__name__)


class Config:
    def __init__(self, filename):
        # Перевіряємо, чи встановлена змінна оточення USE_ENV_CONFIG в true
        use_env_config = os.getenv("USE_ENV_CONFIG", "false").lower() == "true"

        if not use_env_config:
            # Якщо змінна USE_ENV_CONFIG не встановлена в true, читаємо конфігураційний файл
            self.parser = configparser.ConfigParser(interpolation=None)
            self.parser.read(filename)
        else:
            # Якщо змінна USE_ENV_CONFIG встановлена в true, ігноруємо конфігураційний файл
            self.parser = None

            # Функція для отримання значення з змінної оточення або конфігураційного файлу

        def get_config_value(section, option, default=None, required=False):
            env_var = f"{section.upper()}_{option.upper()}"
            if use_env_config:
                # Якщо використовуємо змінні оточення, зчитуємо значення тільки з них
                value = os.getenv(env_var, default)
            else:
                # Якщо змінна USE_ENV_CONFIG пуста, використовуємо тільки файл конфігурації
                value = self.parser.get(section, option, fallback=default)

            # Перевірка на обов'язковість параметра
            if required and not value:
                err_str = f"Помилка: Змінна оточення '{section.upper()}_{option.upper()}' є обовʼязковою. Задайте її значення будь ласка."
                logger.critical(err_str)
                raise ValueError(err_str)  #

            return value

        # Зчитування конфігурації
        # База даних Redis
        self.redis_host = get_config_value('redis', 'host', required=True)
        self.redis_port = get_config_value('redis', 'port', required=True)
        self.redis_db = get_config_value('redis', 'db', required=True)
        # Параметри логування
        self.log_filename = get_config_value('logging', 'filename')
        self.log_filemode = get_config_value('logging', 'filemode', 'a')
        self.log_format = get_config_value('logging', 'format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        self.log_dateformat = get_config_value('logging', 'dateformat', '%Y-%m-%d %H:%M:%S')
        self.log_level = get_config_value('logging', 'level', 'INFO', required=True)

    def get(self, section, option):
        return self.parser.get(section, option)

def configure_logging(config_instance):
    log_filename = config_instance.log_filename
    log_filemode = config_instance.log_filemode
    log_format = config_instance.log_format
    log_datefmt = config_instance.log_dateformat
    log_level = config_instance.log_level

    #Якщо log_filename не передано, логування відбувається у консоль.
    if log_filename:
        # Логування у файл
        logging.basicConfig(
            filename=log_filename,
            filemode=log_filemode,
            format=log_format,
            datefmt=log_datefmt,
            level=getattr(logging, log_level, logging.INFO)
        )
        logger.info("Логування налаштовано")

    else:
        # Логування в консоль для Docker
        logging.basicConfig(
            format=log_format,
            datefmt=log_datefmt,
            level=log_level,
            handlers=[logging.StreamHandler()]  # Вывод в stdout
        )


# REDIS_HOST = '192.168.99.121'
# REDIS_PORT = 6379
# REDIS_DB = 0
