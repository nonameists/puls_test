import json
import re

import requests
from bs4 import BeautifulSoup as soup

DICT_KEYS = ['complex', 'type', 'phase', 'building', 'section', 'price_base',
             'price_finished', 'price_sale', 'price_finished_sale', 'area',
             'number', 'number_on_site', 'rooms', 'floor', 'in_sale',
             'sale_status', 'finished', 'currency', 'ceil', 'article',
             'finishing_name', 'furniture', 'furniture_price', 'plan',
             'feature', 'view', 'euro_planning', 'sale', 'discount_percent',
             'discount', 'comment']


class NdvParser:
    def __init__(self):
        self.session = requests.Session()
        self.base_url = 'https://www.ndv.ru'
        self.base_url_flats = 'https://www.ndv.ru/novostrojki/flats'
        self.new_buildings_url = 'https://www.ndv.ru/novostrojki'
        self.parser_dict = dict.fromkeys(DICT_KEYS)
        self.objects_list = self._get_new_buildings(self.new_buildings_url)

    def get_flats_data(self):
        """
        Метод для получения данных о продаже квартир в новостройках
        Возвращает список словарей с данными о квартирах
        :return: list of dicts
        """
        # исходный список объектов который будем возвращать
        objects = []
        raw_data = self.session.get(self.base_url_flats).content
        content = soup(raw_data, 'html.parser')
        # Поиск паджинатора на странице
        pages = self._find_pagination(content)

        if pages:
            for i in range(1, pages+1):
                page_url = self.base_url_flats + f'?page={i}'
                raw_data = self.session.get(page_url).content
                content = soup(raw_data, 'html.parser')
                # добавляем(объединяем) в исходный список
                objects.extend(self._write_flats_data(content))

        else:
            objects = self._write_flats_data(content)

        return objects

    def get_parking_data(self):
        """
        Метод для получения данных о продаже парковочных мест
        Возвращает список словарей с данными о парковочных местах
        :return: list of dicts
        """
        objects = []
        # Итерируемся по списку ЖК
        for item in self.objects_list:
            # забираем имя ЖК и ссылку на его страницу. Добавляем к URL /parking
            location, url = item
            url += '/parking'
            answer = self.session.get(url)
            # проверка есть ли в продаже парковочне места. Если нет, берем следующий ЖК
            if answer.status_code == 404:
                continue
            raw_data = answer.content
            content = soup(raw_data, 'html.parser')
            # Поиск кнопки <<Показать n предложений>>. Поиск кол-ва предложений о продаже
            row = content.find('a', id='NewBuildingComplexUpdateButton').get_text(strip=True)
            number = int(re.search('(?P<number>\d+)', row).group())
            # Если страница есть, но в данный момент 0 предложений, берем следующий ЖК
            if not number:
                continue
            # Поиск паджинатора на странице
            pages = self._find_pagination(content)

            if pages:
                for i in range(1, pages+1):
                    page_url = url + f'?page={i}'
                    raw_data = self.session.get(page_url).content
                    content = soup(raw_data, 'html.parser')
                    # добавляем(объединяем) в исходный список
                    objects.extend(self._write_parking_data(content, location))

            else:
                objects.extend(self._write_parking_data(content, location))
        return objects

    def get_full_data(self, json_file=None):
        """
        Метод парсит данные о квартирах в новостройках + данные о парковочных местах
        Записывает полученные данные в json файл
        :return: list of dicts - if json_file=None
        :return: json_file - if json_file=True
        """

        print('Starting data parsing...')
        flats = self.get_flats_data()

        parking = self.get_parking_data()
        data_result = flats + parking

        if json_file is None:
            return data_result
        else:
            with open('ndv_ru.json', 'w') as file:
                json.dump(data_result, file)
                print('Success')

    def _get_new_buildings(self, url):
        """
        Метод возвращает список кортежей с именем ЖК и его URL
        :param url: str
        :return: list of tuples
        [('Мкр. «Мегаполис»(Москва, ВАО, Салтыковская улица 8с22)','/novostrojki/zhk/mkr-megapolis')]
        """
        objects = []
        raw_data = self.session.get(url).content
        content = soup(raw_data, 'html.parser')
        # Поиск паджинатора на странице
        pages = self._find_pagination(content)

        if pages:
            for i in range(1, pages + 1):
                # добавляем ?page=n к URL
                page_url = self.new_buildings_url + f'?page={i}'
                raw_data = self.session.get(page_url).content
                content = soup(raw_data, 'html.parser')
                # добавляем(объединяем) в исходный список
                objects.extend(self._get_objects(content))
        else:
            objects = self._get_objects(content)

        return objects

    def _get_objects(self, data):
        """
        Функция принимает на вход объект класса bs4.BeautifulSoup.
        Ищет название жк, регион и ссылку на объект ЖК
        :param data: bs4.BeautifulSoup
        :return: list of tuples
        [('Мкр. «Мегаполис»(Москва, ВАО, Салтыковская улица 8с22)','/novostrojki/zhk/mkr-megapolis')]
         """
        output = []
        raw_data = data.find_all('div', {'class': 'tile__content'})

        for item in raw_data:
            name = item.select_one('a', {'class': 'tile__name'}).text.strip()
            location = item.find('span', {'class': 'tile__location'}).get_text().strip()
            urn = item.select_one('a', {'class': 'tile__name'}).get('href')
            output.append((name + f'({location})', self.base_url + urn))

        return output

    def _find_pagination(self, data):
        """
        Функция принимает на вход объект класса bs4.BeautifulSoup.
        Производит поиск пагинатора. Если он есть то возвращает номер последней страницы.
        :param data: bs4.BeautifulSoup
        :return: int last page number or False
        """
        pages = data.findAll('a', {'class': 'move-to-page'})
        if pages:
            last_page = int(pages[-2].text)
            return last_page
        return False

    def _get_image(self, data):
        """
        Метод для парсинга схемы квартиры
        На вход принимает bs4.element.Tag. Производит поиск по div
        классу tile__image. С помощью регулярного выражения забирает URL
        :param data: bs4.element.Tag
        :return: str (image src url)
        """
        try:
            plan = data.find('div', class_='tile__image')['data-deskstop']
            plan = re.search("url\('(?P<url>\S+)'\)", plan).group('url')
            return plan
        except AttributeError:
            return None

    def _get_complex(self, data):
        """
        Метод для поиска имени ЖК и его региона
        :param data: bs4.element.Tag
        :return: str
        """
        try:
            complex = data.find(
                'a',
                class_='tile__resale-complex--link js_tile_complex_link'
            ).get_text(
                strip=True
            )
            location = data.find('span', class_='tile__location').get_text(strip=True)
            complex += f'({location})'
            return complex

        except AttributeError:
            return None

    def _get_phase(self, data):
        """
        Метод для поиска очереди строительства
        :param data: bs4.element.Tag
        :return: str
        """
        try:
            phase = data.find('span', class_='tile__row--resale_date').get_text(strip=True)
            return phase
        except AttributeError:
            return None

    def _price_base(self, data):
        """
        Метод для поиска цены квартиры
        :param data: bs4.element.Tag
        :return: str
        """
        try:
            price_base = data.find('span', class_='tile__price').get_text(strip=True)
            price_base = int(''.join(price_base.split()[:3]))
            return price_base
        except AttributeError:
            return None

    def _get_complex_item(self, data):
        """
        Метод для поиска информации о квартире
        Поиск корпуса, секции, этажа и номера квартиры
        Возвращает словарь с ключами ['section', 'floor', 'number', 'building']
        :param data: bs4.element.Tag
        :return: dict
        """
        keys = ('section', 'floor', 'number', 'building')
        result = dict.fromkeys(keys)

        info = data.find_all('div', class_='tile__in-complex-item')

        for item in info:
            title = item.select_one('.tile__in-complex-title').get_text(strip=True).lower()
            value = item.select_one('.tile__in-complex-value').get_text(strip=True)

            if title == 'корпус':
                result['building'] = value
            elif title == 'секция':
                result['section'] = value
            elif title == 'этаж':
                result['floor'] = value
            elif title == 'номер':
                result['number'] = value

        return result

    def _get_dimentions(self, data):
        """
        Метод производит поиск кол-ва комнат в квартире, площади + определение типа апартаменты/квартира
        :param data: bs4.element.Tag
        :return: dict
        """
        result = dict()
        name = data.find('a', {'class': 'tile__name'}).get_text(strip=True)
        result['area'] = float(name.split()[-1].replace('м²', '').replace(',', '.'))

        if 'студия' in name.split()[0].lower():
            result['rooms'] = 'studio'
        else:
            result['rooms'] = int(name.split('-')[0])

        if 'апартамент' in name.lower():
            result['type'] = 'apartment'
        else:
            result['type'] = 'flat'

        return result

    def _write_flats_data(self, data):
        """
        Метод для записи данных о отдельной квартире в словарь
        На вход принимает объект класса bs4.BeautifulSoup
        :param data: bs4.BeautifulSoup
        :return: list of dict
        """
        result = []
        # Поиск отдельных объектов объявлений на странице
        raw_data = data.find_all('div', class_='tile__link js-tile-link')
        # в цикле проходим по каждому объявлению
        for item in raw_data:
            # Бремем копию исходного словаря с ключами в который будем записывать данные
            output = self.parser_dict.copy()
            # записываем имя ЖК и его регион
            output['complex'] = self._get_complex(item)
            # записываем очередь строительства
            output['phase'] = self._get_phase(item)
            # записываем цену
            output['price_base'] = self._price_base(item)
            # записвыем ссылку на план объекта
            output['plan'] = self._get_image(item)
            # обновляем в словаре ключи с данными для корпуса, секции, этажа и номера квартиры
            output.update(self._get_complex_item(item))
            # обновляем в словаре ключи с данными для комнат в квартире, площади + типа квартиры
            output.update(self._get_dimentions(item))
            # добавляем словарь в список который будем возвращать
            result.append(output)

        return result

    def _write_parking_data(self, data, location):
        """
        Метод для записи данных о отдельном парковочном месте
        На вход принимает объект класса bs4.BeautifulSoup
        :param data: bs4.BeautifulSoup
        :param location: str
        :return: list of dicts
        """
        result = []
        # Поиск отдельных объектов парковочных мест на сранице ЖК
        raw_data = data.find_all('a', class_='flats-table__row table-body--row')
        # в цикле проходим по каждому парковочному месту
        for item in raw_data:
            # Бремем копию исходного словаря с ключами в который будем записывать данные
            output = self.parser_dict.copy()
            # записываем имя ЖК и регион
            output['complex'] = location
            # записываем данные о парковочном месте (площаь, корпус, секция, этаж, план)
            output.update(self._get_parking_info(item))
            # добавляем словарь в список который будем возвращать
            result.append(output)

        return result

    def _get_parking_info(self, data):
        """
        Метод для парсинга данных о парковочном месте
        :param data: bs4.element.Tag
        :return: dict
        """

        plan_img = None
        price_base = None
        price_sale = None
        building = None
        area = None
        section = None
        floor = None
        number = None

        urn = data.get('href')
        parking_url = self.base_url + urn
        parking_data = soup(self.session.get(parking_url).content, 'html.parser')

        # поиск номера парковочного места
        raw_number = parking_data.find('meta', {'content': '10'})
        if raw_number:
            number = raw_number.previous.strip().split()[1].replace('№', '')
        else:
            try:
                number = parking_data.find('h1', class_='title').get_text(strip=True).split()[2]
            except AttributeError:
                pass

        # поиск ссылки на план
        try:
            plan_div = parking_data.find('div', {'id': 'plans_layout'})
            plan_img = plan_div.find('img').get('src')
        except AttributeError:
            pass

        # поиск цены (в том числе со скидкой)
        try:
            price_base = parking_data.find('span', class_='card__info-prices__price').get_text(strip=True)
            price_base = int(price_base.split('руб.')[0].replace(' ', ''))
        except AttributeError:
            try:
                price_base = parking_data.find('span', class_='card__info-prices__old').get_text(strip=True)
                price_base = int(price_base.split('руб.')[0].replace(' ', ''))

                price_sale = parking_data.find(
                    'span',
                    class_='card__info-prices__price card__info-prices--red'
                ).get_text(strip=True)
                price_sale = int(price_sale.split('руб.')[0].replace(' ', ''))
            except AttributeError:
                pass

        # парсинг данных о парковочном месте(метраж, копус, секцияб этаж)
        parking_div_info = parking_data.find('div', class_='card__info-row card__info-row--settings')
        parking_div_data = parking_div_info.find_all('div', class_='card__info-params__number')

        # парсинг площади
        try:
            raw_area = parking_div_data[0].get_text(strip=True).split()[0]
            area = float(raw_area.replace(',', '.'))
        except (AttributeError, IndexError):
            pass
        # парсинг корпуса
        try:
            building = parking_div_data[1].get_text(strip=True)
        except (AttributeError, IndexError):
            pass
        # парсинг секции
        try:
            section = parking_div_data[2].get_text(strip=True)
        except (AttributeError, IndexError):
            pass
        # парсинг этажа
        try:
            floor = parking_div_data[3].get_text(strip=True)
        except (AttributeError, IndexError):
            pass

        output_dict = {
            'number': number,
            'building': building,
            'area': area,
            'price_sale': price_sale,
            'price_base': price_base,
            'type': 'parking',
            'plan': plan_img,
            'section': section,
            'floor': floor
        }

        return output_dict


if __name__ == '__main__':
    ndv = NdvParser()
    # Запускаем парсер на квартиры и машиноместа.
    # Данные записываются в json файл
    ndv.get_full_data(json_file=True)

