import re
from typing import Dict, Optional, List
from datetime import datetime
from pathlib import Path


class InvoiceDataExtractor:
    """Извлекает структурированные данные из текста счётов/инвойсов."""
    
    UNRECOGNIZED_FIELD_VALUE = "НЕ_РАСПОЗНАНО"
    
    def __init__(self, use_ml_validation: bool = False, model_path: Optional[str] = None):
        """Инициализация. Опционально включает ML-валидацию извлечённых полей."""
        self.use_ml_validation = use_ml_validation
        self.ml_classifier = None
        
        if use_ml_validation:
            try:
                from app.ml_model import InvoiceFieldClassifier
                self.ml_classifier = InvoiceFieldClassifier()
                
                if model_path is None:
                    possible_paths = [
                        Path("models/invoice_classifier.pkl"),
                        Path("../models/invoice_classifier.pkl"),
                        Path(__file__).parent.parent / "models" / "invoice_classifier.pkl"
                    ]
                    
                    for path in possible_paths:
                        if path.exists():
                            model_path = str(path)
                            break
                
                if model_path and Path(model_path).exists():
                    self.ml_classifier.load(model_path)
                    print(f"✅ ML модель загружена из {model_path}")
                else:
                    print("⚠️ ML модель не найдена. Валидация будет отключена.")
                    self.use_ml_validation = False
            except ImportError:
                print("⚠️ Не удалось импортировать ML модель. Валидация будет отключена.")
                self.use_ml_validation = False
            except Exception as e:
                print(f"⚠️ Ошибка при загрузке ML модели: {e}. Валидация будет отключена.")
                self.use_ml_validation = False
        
        self.patterns = {
            'invoice_number': [
                r'сч[ёе]т[а-я]*\s+на\s+оплату\s+№\s*([\d/]+)',
                r'сч[ёе]т[а-я]*\s*№\s*([\d/]+)',
                r'сч[ёе]т[а-я]*-оферта\s+(\d+)',
                r'сч[ёе]т[а-я]*-фактура\s+№\s*(\d+)',
                r'(?:сч[ёе]т[а-я]*|invoice)\s*[:\-]?\s*№?\s*([\d/]{1,15})(?!\d)',
                r'invoice\s*#?\s*(\d{1,10})',
                r'№\s*([\d/]+)',
            ],
            'date': [
                r'от\s+(\d{1,2}\.\d{1,2}\.\d{4})',
                r'от\s+(\d{1,2}\s+[а-я]+\s+\d{4}\s+г\.)',
                r'(?:дата|date|от)\s*[:\-]?\s*(\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4})',
                r'(\d{1,2}\.\d{1,2}\.\d{4})',
                r'(\d{1,2}/\d{1,2}/\d{4})',
            ],
            'seller': [
                r'поставщик\s+((?:ООО|АО)\s+ТД\s+"[^"]+")',
                r'поставщик\s+((?:ООО|АО)\s+ТД\s+[А-Яа-яA-Za-z]{3,}[А-Яа-яA-Za-z\s,\.]*)',
                r'поставщик\s+((?:ООО|АО|ТД|ИП)\s+"[^"]+")',
                r'поставщик\s+((?:ООО|АО|ТД|ИП)\s+[А-Яа-яA-Za-z]{3,}[А-Яа-яA-Za-z\s,\.]*)',
                r'поставщик[^\n]*?\n\s*((?:ООО|АО)\s+ТД\s+"[^"]+")',
                r'поставщик[^\n]*?\n\s*((?:ООО|АО)\s+ТД\s+[А-Яа-яA-Za-z]{3,}[А-Яа-яA-Za-z\s,\.]*)',
                r'поставщик[:\-]?\s+((?:ООО|АО)\s+ТД\s+"[^"]+")(?:\s+ИНН|\s+КПП|\s+Адрес|$)',
                r'поставщик[:\-]?\s+((?:ООО|АО)\s+ТД\s+[А-Яа-яA-Za-z]{3,}[А-Яа-яA-Za-z\s,\.]*?)(?:\s+ИНН|\s+КПП|\s+Адрес|$)',
                r'поставщик[:\-]?\s+((?:ООО|АО|ТД|ИП)\s+"[^"]+")(?:\s+ИНН|\s+КПП|\s+Адрес|$)',
                r'поставщик[:\-]?\s+((?:ООО|АО|ТД|ИП)\s+[А-Яа-яA-Za-z]{3,}[А-Яа-яA-Za-z\s,\.]*?)(?:\s+ИНН|\s+КПП|\s+Адрес|$)',
                r'поставщик[^п]*?[:\-]?\s*((?:ООО|АО)\s+ТД\s+"[А-Яа-яA-Za-z\s,\.]+")(?![^п]*покупатель)',
                r'поставщик[^п]*?[:\-]?\s*((?:ООО|АО)\s+ТД\s+[А-Яа-яA-Za-z\s,\.]{3,}?)(?:\s+ИНН|\s+КПП)(?![^п]*покупатель)',
                r'исполнитель[:\-]?\s+((?:ООО|АО|ТД|ИП)\s+"[^"]+")(?:\s+ИНН|\s+КПП|\s+Адрес|$)',
                r'продавец[:\-]?\s+((?:ООО|АО|ТД|ИП)\s+"[^"]+")(?:\s+ИНН|\s+КПП|\s+Адрес|$)',
                r'поставщик[^:]*[:\-]?\s*(ИП\s+[А-Яа-яA-Za-z\s,\.]+?)(?:\s+ИНН|\s+КПП|\с+Адрес|$)',
                r'отправитель\s*[:\-]?\s*([А-Я][а-я]+\s+[А-Я][а-я]+)',
            ],
            'buyer': [
                r'покупатель\s+((?:ООО|АО|ТД|ИП)\s+"[^"]+")',
                r'покупатель\s+((?:ООО|АО|ТД|ИП)\s+[А-Яа-яA-Za-z]{2,}[А-Яа-яA-Za-z\s,\.]*)',
                r'покупатель[^\n]*?\n\s*((?:ООО|АО|ТД|ИП)\s+"[^"]+")',
                r'покупатель[^\n]*?\n\s*((?:ООО|АО|ТД|ИП)\s+[А-Яа-яA-Za-z]{2,}[А-Яа-яA-Za-z\s,\.]*)',
                r'покупатель[:\-]?\s+((?:ООО|АО|ТД|ИП)\s+"[^"]+")(?:\s+ИНН|\s+КПП|\s+Адрес|$)',
                r'покупатель[:\-]?\s+((?:ООО|АО|ТД|ИП)\s+[А-Яа-яA-Za-z]{2,}[А-Яа-яA-Za-z\s,\.]*?)(?:\s+ИНН|\s+КПП|\s+Адрес|$)',
                r'заказчик[:\-]?\s+((?:ООО|АО|ТД|ИП)\s+"[^"]+")(?:\s+ИНН|\s+КПП|\s+Адрес|$)',
                r'клиент[:\-]?\s+((?:ООО|АО|ТД|ИП)\s+"[^"]+")(?:\s+ИНН|\s+КПП|\s+Адрес|$)',
                r'покупатель[^:]*[:\-]?\s*(ИП\s+[А-Яа-яA-Za-z\s,\.]+?)(?:\с+ИНН|\с+КПП|\с+Адрес|$)"?',
                r'получатель\s*[:\-]?\s*([А-Я][а-я]+\s+[А-Я]\.)',
                r'получатель\s*[:\-]?\s*([А-Я][а-я]+\s+[А-Я][а-я]+)',
            ],
            'inn': [
                r'поставщик[^п]*?ИНН\s*[:\-]?\s*(\d{10,12})(?![^п]*покупатель)',
                r'исполнитель[^п]*?ИНН\s*[:\-]?\s*(\d{10,12})(?![^п]*покупатель)',
                r'продавец[^п]*?ИНН\s*[:\-]?\s*(\d{10,12})(?![^п]*покупатель)',
                r'поставщик[^:]*[:\-]?[^\d]*ИНН\s*[:\-]?\s*(\d{10,12})',
                r'исполнитель[^:]*[:\-]?[^\d]*ИНН\s*[:\-]?\s*(\d{10,12})',
                r'продавец[^:]*[:\-]?[^\d]*ИНН\s*[:\-]?\s*(\d{10,12})',
            ],
            'kpp': [
                r'поставщик[^п]*?КПП\s*[:\-]?\s*(\d{9})(?![^п]*покупатель)',
                r'исполнитель[^п]*?КПП\s*[:\-]?\s*(\d{9})(?![^п]*покупатель)',
                r'продавец[^п]*?КПП\s*[:\-]?\s*(\d{9})(?![^п]*покупатель)',
                r'поставщик[^:]*[:\-]?[^\d]*КПП\s*[:\-]?\s*(\d{9})',
                r'исполнитель[^:]*[:\-]?[^\d]*КПП\s*[:\-]?\s*(\d{9})',
                r'продавец[^:]*[:\-]?[^\d]*КПП\s*[:\-]?\s*(\d{9})',
            ],
            'total_amount': [
                r'всего\s+к\s+оплате\s*[:\-]?\s*([\d\s,\.]{3,}[,\.]\d{2})',
                r'всего\s+с\s+ндс\s*[:\-]?\s*([\d\s,\.]{3,}[,\.]\d{2})',
                r'к\s+оплате\s*[:\-]?\s*([\d\s,\.]{3,}[,\.]\d{2})',
                r'итого[^,]*вкл[^,]*ндс[^,]*[:\-]?\s*([\d\s,\.]{3,}[,\.]\d{2})',
                r'итого\s*[:\-]?\s*([\d\s,\.]{3,}[,\.]\d{2})\s*(?:руб|RUB|₽|р\.)',
                r'(?:итого|total)\s*[:\-]?\s*([\d\s,\.]{3,}[,\.]\d{2})',
                r'([\d\s,\.]{3,}[,\.]\d{2})\s*(?:руб|RUB|₽|р\.)\s*(?:итого|total)',
                r'сумма\s+([\d\s,\.]{3,}[,\.]\d{2})',
                r'на\s+сумму\s+([\d\s,\.]{3,}[,\.]\d{2})\s*(?:руб|RUB|₽|р\.)',
            ],
            'vat': [
                r'в\s+том\s+числе\s+ндс\s*\d*\s*%\s*[:\-]?\s*([\d\s,\.]{3,}[,\.]\d{2})',
                r'ндс\s*\(?\d+\s*%\)?\s*[:\-]?\s*([\d\s,\.]{3,}[,\.]\d{2})',
                r'(?:НДС|VAT|vat)\s*[:\-]?\s*([\d\s,\.]{3,}[,\.]\d{2})\s*(?:руб|RUB|%)',
                r'НДС\s*(\d+)\s*%\s*[:\-]?\s*([\d\s,\.]{3,}[,\.]\d{2})',
                r'в\s+том\s+числе\s+ндс\s*[:\-]?\s*([\d\s,\.]{3,}[,\.]\d{2})',
            ],
        }
    
    def extract_invoice_data(self, text: str, tables: Optional[List] = None, pdf_path: Optional[str] = None) -> Dict:
        """Формирует структурированный словарь по тексту счёта (invoice, supplier, customer, позиции, суммы)."""
        text_clean = self._preprocess_text(text)
        
        buyer_phone = self._extract_buyer_phone(text_clean)
        
        invoice_number = self._extract_field(text_clean, 'invoice_number')
        invoice_date = self._extract_field(text_clean, 'date')
        seller_name = self._extract_field(text_clean, 'seller')
        buyer_name = self._extract_field(text_clean, 'buyer')
        
        result = {
            'invoice': self._build_invoice_section(text_clean, invoice_number, invoice_date),
            'supplier': self._build_supplier_section(text_clean, seller_name, buyer_phone),
            'customer': self._build_customer_section(text_clean, buyer_name, buyer_phone),
            'line_items': self._extract_line_items_structured(text_clean, tables),
            'financial_summary': self._build_financial_summary(text_clean),
            'signatories': self._extract_signatories(text_clean),
            'terms_and_conditions': self._extract_terms_and_conditions(text_clean),
            'additional_info': self._extract_additional_info(text_clean),
        }
        
        return self._clean_result(result)
    
    def _preprocess_text(self, text: str) -> str:
        """Минимальная нормализация пробелов, переносы строк сохраняются."""
        text = re.sub(r'[ \t]+', ' ', text)
        return text
    
    def _extract_field(self, text: str, field_name: str) -> Optional[str]:
        """Возвращает значение поля по набору регулярных выражений."""
        patterns = self.patterns.get(field_name, [])
        
        if field_name in ['seller', 'buyer']:
            debug_text = ""
            if field_name == 'seller':
                match = re.search(r'поставщик[^\n]{0,200}', text, re.IGNORECASE)
                if match:
                    debug_text = match.group(0)
            elif field_name == 'buyer':
                match = re.search(r'покупатель[^\n]{0,200}', text, re.IGNORECASE)
                if match:
                    debug_text = match.group(0)
            if debug_text:
                print(f"DEBUG {field_name}: Найден фрагмент: {debug_text[:100]}")
        
        for pattern_idx, pattern in enumerate(patterns):
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                if match.lastindex and match.lastindex >= 1:
                    value = match.group(1)
                else:
                    value = match.group(0)
                if value:
                    if field_name in ['seller', 'buyer']:
                        print(f"DEBUG {field_name}: Паттерн #{pattern_idx} нашел: '{value}'")
                    if field_name == 'invoice_number':
                        value_clean = value.strip()
                        if len(value_clean) > 10:
                            continue
                    if field_name in ['seller', 'buyer']:
                        value_clean = value.strip()
                        if (re.match(r'^[a-zа-я]\s*[,]?$', value_clean, re.IGNORECASE) or
                            re.match(r'^0+$', value_clean) or
                            re.match(r'^\d+$', value_clean) or
                            len(value_clean) < 3):
                            continue
                    value = re.sub(r'\s+', ' ', value.strip())
                    if field_name == 'total_amount':
                        value = value.replace(' ', '')
                    if field_name in ['seller', 'buyer']:
                        stop_words = ['Карта', 'Получатель', 'Квитанция', 'По вопросам', 'получателя', 'карта', 'Карта получателя', 'Служба', 'ИНН', 'КПП', 'Адрес']
                        min_idx = len(value)
                        for word in stop_words:
                            idx = value.lower().find(word.lower())
                            if idx > 0 and idx < min_idx:
                                min_idx = idx
                        if min_idx < len(value):
                            value_before = value
                            value = value[:min_idx].strip()
                            if '"' in value and value.count('"') % 2 == 1:
                                value = value + '"'
                        
                        value = re.sub(r'\s+[a-z]\s*$', '', value, flags=re.IGNORECASE)
                        value = re.sub(r'\s*[,]+$', '', value)
                        
                        if len(value) < 3 or (re.match(r'^[a-z]\s*[,]?$', value)) or (re.match(r'^[a-zA-Z\s,]+$', value) and len(value.split()) < 2):
                            if field_name == 'buyer':
                                buyer_patterns = [
                                    r'покупатель\s+(ООО\s+"[А-Яа-яA-Za-z\s,\.]+")(?:\s+ИНН|\s+КПП|\s+Адрес|$)',
                                    r'покупатель\s+(ООО\s+[А-Яа-яA-Za-z\s,\.]{3,}?)(?:\s+ИНН|\s+КПП|\s+Адрес|$)',
                                    r'покупатель[^:]*[:\-]?\s*(ООО\s+"[А-Яа-яA-Za-z\s,\.]+")(?:\s+ИНН|\s+КПП|\s+Адрес|$)"?',
                                    r'покупатель[^:]*[:\-]?\s*(ООО\s+"[А-Яа-яA-Za-z\s,\.]+?)(?:\s+ИНН|\s+КПП|\s+Адрес|$)"?',
                                    r'заказчик[^:]*[:\-]?\s*(ООО\s+"[А-Яа-яA-Za-z\s,\.]+?)(?:\s+ИНН|\s+КПП|\с+Адрес|$)"?',
                                    r'получатель\s+([А-Я][а-я]+\s+[А-Я]\.)',
                                    r'получатель\s+([А-Я][а-я]+\s+[А-Я][а-я]+)',
                                ]
                                for pattern in buyer_patterns:
                                    match = re.search(pattern, text, re.IGNORECASE)
                                    if match:
                                        value = match.group(1)
                                        break
                            elif field_name == 'seller':
                                seller_patterns = [
                                    r'поставщик[^:]*[:\-]?\s*((?:ООО|АО)\s*ТД\s*"?[А-Яа-яA-Za-z\s,\.]+")(?:\s+ИНН|\s+КПП|\s+Адрес|$)',
                                    r'поставщик[^:]*[:\-]?\s*((?:ООО|АО)\s*ТД\s*[А-Яа-яA-Za-z\s,\.]{3,}?)(?:\s+ИНН|\s+КПП|\s+Адрес|$)',
                                    r'поставщик[^:]*[:\-]?\s*(ООО\s*"?[А-Яа-яA-Za-z\s,\.]+?)(?:\s+ИНН|\s+КПП|\s+Адрес|$)"?',
                                    r'исполнитель[^:]*[:\-]?\s*(ООО\s*"?[А-Яа-яA-Za-z\s,\.]+?)(?:\s+ИНН|\s+КПП|\s+Адрес|$)"?',
                                    r'отправитель\s+([А-Я][а-я]+\s+[А-Я][а-я]+)',
                                ]
                                for pattern in seller_patterns:
                                    match = re.search(pattern, text, re.IGNORECASE)
                                    if match:
                                        value = match.group(1)
                                        break
                        
                        value = value.strip()
                        
                        if field_name in ['seller', 'buyer']:
                            print(f"DEBUG {field_name}: После очистки: '{value}'")
                        
                        if field_name in ['seller', 'buyer']:
                            value_clean = value.strip()
                            if len(value_clean) < 3 or re.match(r'^[a-zа-я]\s*[,]?$', value_clean, re.IGNORECASE):
                                print(f"DEBUG {field_name}: Значение '{value_clean}' слишком короткое, пробуем следующий паттерн")
                                continue
                        
                    if self.use_ml_validation and self.ml_classifier:
                        try:
                            is_valid, confidence = self.ml_classifier.validate_extraction(
                                field_name, value, text
                            )
                            if not is_valid and confidence < 0.5:
                                continue
                        except Exception as e:
                            pass
                        
                    return value
        
        return None
    
    def _extract_items(self, text: str) -> Optional[List[Dict]]:
        """Пытается разобрать строки товарной таблицы (в т.ч. при кривом OCR)."""
        items = []
        lines = text.split('\n')
        
        in_items_section = False
        items_start_keywords_priority = [
            r'перечень\s+товаров', r'перечень\s+товаров.*работ.*услуг',
            r'заказные\s+позиции', r'позиции\s+заказа', 
            r'товар', r'товары', r'услуг', r'работ', 
            r'контрактное\s+производство',
            r'счет.*договор.*товар'
        ]
        items_start_keywords_secondary = [
            r'наименование\s+товара', r'наименование\s+товаров',
            r'наименование.*работ.*услуг', r'наименование',
            r'№\s*\d+', 'описание'
        ]
        items_end_keywords = [
            r'^итого\s*$',
            r'^всего\s+наименований',
            r'^ндс\s*\(',
            r'^всего\s+с\s+ндс\s*$',
            r'^всего\s+к\s+оплате',
            r'^итого\s+без\s+ндс',
        ]
        
        header_found = False
        print(f"DEBUG items: Начинаю поиск товаров, всего строк: {len(lines)}")
        for i, line in enumerate(lines):
            line_clean = line.strip()
            if not line_clean:
                continue
            
            if not in_items_section:
                if any(re.search(keyword, line_clean, re.IGNORECASE) for keyword in items_start_keywords_priority):
                    in_items_section = True
                    print(f"DEBUG items: Начало секции товаров найдено на строке {i} (приоритетное): {line_clean[:50]}")
                    if any(keyword in line_clean.lower() for keyword in ['наименование', 'ед', 'кол-во', 'цена', 'сумма']):
                        header_found = True
                    continue
                elif any(re.search(keyword, line_clean, re.IGNORECASE) for keyword in items_start_keywords_secondary):
                    if any(keyword in line_clean.lower() for keyword in ['наименование', 'ед', 'кол-во', 'цена', 'сумма']):
                        in_items_section = True
                        header_found = True
                        print(f"DEBUG items: Начало секции товаров найдено на строке {i} (заголовок таблицы): {line_clean[:50]}")
                    continue
            
            if in_items_section:
                if i < len(lines) - 1:
                    print(f"DEBUG items: Обрабатываю строку {i} в секции товаров: {line_clean[:80]}")
                
                starts_with_number = re.match(r'^\d+\s', line_clean)
                has_amount = re.search(r'[\d\s]{3,}[,\.]\d{2}', line_clean)
                
                if starts_with_number or has_amount:
                    pass
                else:
                    is_category = (
                        len(line_clean) > 10 and 
                        any(keyword in line_clean.lower() for keyword in ['производство', 'товар', 'услуг', 'работ']) and
                        re.search(r'^(перечень|наименование|категория|№|номер)', line_clean, re.IGNORECASE)
                    )
                    
                    if is_category:
                        print(f"DEBUG items: Пропущена категория товара на строке {i}: {line_clean[:50]}")
                        continue
                
                header_keywords = ['№', 'изм', 'ед.', 'ед ', 'кол-во', 'цена', 'сумма']
                header_count = sum(1 for keyword in header_keywords if keyword in line_clean.lower())
                is_table_header = header_count >= 3
                starts_with_number = re.match(r'^\d+\s', line_clean)
                if is_table_header and not starts_with_number:
                    print(f"DEBUG items: Пропущен заголовок таблицы на строке {i}: {line_clean[:50]}")
                    continue
                
                if any(re.search(keyword, line_clean, re.IGNORECASE) for keyword in items_end_keywords):
                    print(f"DEBUG items: Конец секции товаров на строке {i}: {line_clean[:50]}")
                    break
                
                if re.search(r'^итого\s*$|^всего\s*$|итого\s+без\s+ндс|всего\s+с\s+ндс', line_clean, re.IGNORECASE):
                    print(f"DEBUG items: Пропущена итоговая строка на строке {i}: {line_clean[:50]}")
                    continue
                
                combined_line = line_clean
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    should_combine = (
                        (re.search(r'\d+', line_clean) or re.search(r'[\d\s]{1,}[,\.]\d{2}', line_clean)) and
                        len(next_line) > 0 and
                        not re.search(r'^(итого|всего|ндс)', next_line, re.IGNORECASE) and
                        not re.match(r'^\d+\s', next_line) and
                        len(next_line) < 100
                    )
                    
                    if should_combine:
                        combined_line = line_clean + ' ' + next_line
                        print(f"DEBUG items: Объединены строки {i} и {i+1}: {combined_line[:80]}")
                        
                        if i + 2 < len(lines):
                            next_line2 = lines[i + 2].strip()
                            if (not re.search(r'[\d\s]{3,}[,\.]\d{2}', combined_line) and
                                not re.search(r'^(итого|всего|ндс)', next_line2, re.IGNORECASE) and
                                not re.match(r'^\d+\s', next_line2) and
                                len(next_line2) < 100):
                                combined_line = combined_line + ' ' + next_line2
                                print(f"DEBUG items: Объединены строки {i}, {i+1} и {i+2}: {combined_line[:80]}")
                
                alt_pattern = r'^(\d+)\s+(.+?)\s+(\d+)\s+(шт|кг|м|м2|м3|л|г|т|ед|компл|упак|рул|лист|пог\.м|пог\s*м|шт\.)\s*\.?\s+([\d\s]{1,}[,\.]\d{2})\s+([\d\s]{1,}[,\.]\d{2})'
                match = re.search(alt_pattern, combined_line, re.IGNORECASE)
                if match:
                    name = match.group(2).strip()
                    if len(name) >= 5 and not name.strip().isdigit():
                        print(f"DEBUG items: Строка {i} - альтернативный паттерн совпал: {combined_line[:80]}")
                        is_simple_format = True
                    else:
                        match = None
                        is_simple_format = False
                else:
                    is_simple_format = False
                
                if not match:
                    simple_item_pattern = r'^(\d+)\s+([А-Яа-яA-Za-z0-9\s,\.\-\(\)хХмМ]{10,}?)\s+(\d+)\s+([А-Яа-яA-Za-z]{1,5})\s+([\d\s]{1,}[,\.]\d{2})\s+([\d\s]{1,}[,\.]\d{2})'
                    match = re.search(simple_item_pattern, combined_line)
                    if match:
                        name = match.group(2).strip()
                        if len(name) >= 5:
                            print(f"DEBUG items: Строка {i} - простой паттерн совпал: {combined_line[:80]}")
                            is_simple_format = True
                        else:
                            match = None
                            is_simple_format = False
                
                if not match:
                    item_pattern = r'^(\d+)\s+([А-Яа-яA-Za-z0-9\s,\.\-\(\)]+?)\s+([А-Яа-яA-Za-z]{1,5})\s+(\d+)\s+([^\d]{0,50}?)\s+([\d\s,\.]{3,}[,\.]\d{2})\s+([\d\s,\.]{3,}[,\.]\d{2})\s+([\d\s,\.]{3,}[,\.]\d{2})\s+([\d\s,\.]{3,}[,\.]\d{2})'
                    match = re.search(item_pattern, combined_line)
                    if match:
                        print(f"DEBUG items: Строка {i} - полный паттерн совпал: {combined_line[:80]}")
                        is_simple_format = False
                        is_no_terms = False
                
                if not match:
                    item_pattern_no_terms = r'^(\d+)\s+([А-Яа-яA-Za-z0-9\s,\.\-\(\)]+?)\s+([А-Яа-яA-Za-z]{1,5})\s+(\d+)\s+([\d\s,\.]{3,}[,\.]\d{2})\s+([\d\s,\.]{3,}[,\.]\d{2})\s+([\d\s,\.]{3,}[,\.]\d{2})\s+([\d\s,\.]{3,}[,\.]\d{2})'
                    match = re.search(item_pattern_no_terms, combined_line)
                    if match:
                        print(f"DEBUG items: Строка {i} - паттерн без условий совпал: {combined_line[:80]}")
                    is_no_terms = True
                else:
                    is_no_terms = False
                
                if match:
                    try:
                        if is_simple_format:
                            item = {
                                'number': match.group(1).strip(),
                                'name': match.group(2).strip(),
                                'quantity': match.group(3).strip(),
                                'unit': match.group(4).strip(),
                                'price_without_vat': match.group(5).replace(' ', '').replace(',', '.'),
                                'total_with_vat': match.group(6).replace(' ', '').replace(',', '.'),
                                'amount_without_vat': match.group(6).replace(' ', '').replace(',', '.'),
                                'delivery_terms': None,
                                'vat_amount': None
                            }
                        elif is_no_terms:
                            item = {
                                'number': match.group(1).strip(),
                                'name': match.group(2).strip(),
                                'unit': match.group(3).strip(),
                                'quantity': match.group(4).strip(),
                                'delivery_terms': None,
                                'price_without_vat': match.group(5).replace(' ', '').replace(',', '.') if match.lastindex >= 5 else None,
                                'amount_without_vat': match.group(6).replace(' ', '').replace(',', '.') if match.lastindex >= 6 else None,
                                'vat_amount': match.group(7).replace(' ', '').replace(',', '.') if match.lastindex >= 7 else None,
                                'total_with_vat': match.group(8).replace(' ', '').replace(',', '.') if match.lastindex >= 8 else None,
                            }
                        else:
                            item = {
                                'number': match.group(1).strip(),
                                'name': match.group(2).strip(),
                                'unit': match.group(3).strip(),
                                'quantity': match.group(4).strip(),
                                'delivery_terms': match.group(5).strip() if match.lastindex >= 5 and match.group(5) else None,
                                'price_without_vat': match.group(6).replace(' ', '').replace(',', '.') if match.lastindex >= 6 else None,
                                'amount_without_vat': match.group(7).replace(' ', '').replace(',', '.') if match.lastindex >= 7 else None,
                                'vat_amount': match.group(8).replace(' ', '').replace(',', '.') if match.lastindex >= 8 else None,
                                'total_with_vat': match.group(9).replace(' ', '').replace(',', '.') if match.lastindex >= 9 else None,
                            }
                        items.append(item)
                        print(f"DEBUG items: Извлечен товар #{item.get('number', 'N/A')}: {item.get('name', 'N/A')[:50]}")
                        if combined_line != line_clean:
                            i += 1
                        continue
                    except Exception as e:
                        print(f"DEBUG items: Ошибка при парсинге товара на строке {i}: {e}")
                        print(f"DEBUG items: Строка: {combined_line[:100]}")
                        pass
                
                if not match:
                    simple_pattern = r'^(\d+)\s+([А-Яа-яA-Za-z0-9\s,\.\-\(\)]{5,}?)\s+([А-Яа-яA-Za-z]{1,5})\s+(\d+)'
                    simple_match = re.search(simple_pattern, combined_line)
                    if simple_match:
                        print(f"DEBUG items: Строка {i} - упрощенный паттерн совпал: {combined_line[:80]}")
                    
                    if simple_match:
                        amounts = re.findall(r'([\d\s]{3,}[,\.]\d{2})', combined_line)
                        valid_amounts = [a for a in amounts if len(a.replace(' ', '').replace(',', '.').replace('.', '')) > 3]
                        
                        if len(valid_amounts) >= 3:
                            try:
                                item = {
                                    'number': simple_match.group(1).strip(),
                                    'name': simple_match.group(2).strip(),
                                    'unit': simple_match.group(3).strip(),
                                    'quantity': simple_match.group(4).strip(),
                                    'price_without_vat': valid_amounts[0].replace(' ', '').replace(',', '.') if len(valid_amounts) > 0 else None,
                                    'amount_without_vat': valid_amounts[1].replace(' ', '').replace(',', '.') if len(valid_amounts) > 1 else None,
                                    'vat_amount': valid_amounts[2].replace(' ', '').replace(',', '.') if len(valid_amounts) > 2 else None,
                                    'total_with_vat': valid_amounts[-1].replace(' ', '').replace(',', '.') if len(valid_amounts) > 2 else None,
                                }
                                items.append(item)
                                print(f"DEBUG items: Извлечен товар (упрощенный) #{item.get('number', 'N/A')}: {item.get('name', 'N/A')[:50]}")
                                if combined_line != line_clean:
                                    i += 1
                                continue
                            except Exception as e:
                                print(f"DEBUG items: Ошибка при извлечении товара (упрощенный) на строке {i}: {e}")
                                print(f"DEBUG items: Строка: {combined_line[:100]}")
                                pass
                
                if not match:
                    fallback_pattern = r'(\d+)\s+([А-Яа-яA-Za-z]{1,5})\s+([\d\s]{1,}[,\.]\d{2})\s+([\d\s]{1,}[,\.]\d{2})'
                    fallback_match = re.search(fallback_pattern, combined_line)
                    
                    if not fallback_match:
                        numbers = re.findall(r'\d+', combined_line)
                        amounts = re.findall(r'([\d\s]{3,}[,\.]\d{2})', combined_line)
                        large_numbers = [n for n in numbers if len(n) >= 4]
                        
                        has_potential = (
                            (len(numbers) >= 3 and len(amounts) >= 1) or
                            (len(large_numbers) >= 2) or
                            (len(numbers) >= 4)
                        )
                        
                        if has_potential:
                            unit_match = re.search(r'\d+\s+([А-Яа-яA-Za-z]{1,5})\s+', combined_line)
                            known_units = ['шт', 'кг', 'м', 'л', 'г', 'т', 'ед', 'компл', 'упак']
                            has_unit = unit_match or any(unit in combined_line.lower() for unit in known_units)
                            
                            if has_unit or len(amounts) >= 1 or len(large_numbers) >= 2:
                                fallback_match = True
                                print(f"DEBUG items: Найден потенциальный товар (fallback 2) на строке {i}: {combined_line[:80]}")
                                print(f"DEBUG items: Числа: {numbers}, Суммы: {amounts}, Большие числа: {large_numbers}")
                    
                    if fallback_match:
                        is_total_line = (
                            re.search(r'^(итого|всего|ндс)', combined_line[:30], re.IGNORECASE) or
                            re.search(r'итого\s*[:]', combined_line, re.IGNORECASE) or
                            re.search(r'всего\s+к\s+оплате', combined_line, re.IGNORECASE) or
                            re.search(r'в\s+том\s+числе\s+ндс', combined_line, re.IGNORECASE)
                        )
                        
                        if not is_total_line:
                            try:
                                if isinstance(fallback_match, bool):
                                    numbers = re.findall(r'\d+', combined_line)
                                    amounts = re.findall(r'([\d\s]{3,}[,\.]\d{2})', combined_line)
                                    large_numbers = [n for n in numbers if len(n) >= 4]
                                    
                                    valid_amounts = [a for a in amounts if len(a.replace(' ', '').replace(',', '.').replace('.', '')) > 3]
                                    if len(valid_amounts) < 2 and len(large_numbers) >= 2:
                                        for ln in large_numbers[-2:]:
                                            if len(ln) >= 4:
                                                formatted = ln + ',00'
                                                valid_amounts.append(formatted)
                                    
                                    if (len(valid_amounts) >= 1 and len(numbers) >= 2) or len(large_numbers) >= 2:
                                        known_units = ['шт', 'кг', 'м', 'л', 'г', 'т', 'ед', 'компл', 'упак', 'рул', 'лист']
                                        unit = 'шт'
                                        for u in known_units:
                                            if u in combined_line.lower():
                                                unit = u
                                                break
                                        
                                        if unit == 'шт':
                                            unit_match = re.search(r'\d+\s+([А-Яа-яA-Za-z]{1,5})\s+', combined_line)
                                            if unit_match:
                                                potential_unit = unit_match.group(1).lower()
                                                if len(potential_unit) <= 5 and not potential_unit.isdigit():
                                                    unit = potential_unit
                                        
                                        name_match = re.search(r'([А-Яа-яA-Za-z\s]{5,}?)\s+(\d{1,3})\s+', combined_line)
                                        if name_match:
                                            name = name_match.group(1).strip()
                                            potential_qty = name_match.group(2)
                                            if 1 <= int(potential_qty) <= 999:
                                                name = name
                                                quantity = potential_qty
                                            else:
                                                name = combined_line[:50].strip()
                                                quantity = numbers[1] if len(numbers) > 1 else '1'
                                        else:
                                            name = combined_line[:50].strip()
                                            quantity = numbers[1] if len(numbers) > 1 else '1'
                                        
                                        name = re.sub(r'^\d+\s+', '', name)
                                        name = re.sub(r'^[|\[\]]+\s*', '', name)
                                        
                                        if quantity.isdigit() and int(quantity) > 1000:
                                            small_numbers = [n for n in numbers if 1 <= int(n) <= 999]
                                            quantity = small_numbers[0] if small_numbers else '1'
                                        
                                        if len(name) >= 3 and not re.search(r'^(итого|всего|ндс|b\s+tom|всето)', name[:20], re.IGNORECASE):
                                            price = None
                                            total = None
                                            
                                            if len(valid_amounts) >= 2:
                                                price = valid_amounts[0].replace(' ', '').replace(',', '.')
                                                total = valid_amounts[-1].replace(' ', '').replace(',', '.')
                                            elif len(valid_amounts) == 1:
                                                total = valid_amounts[0].replace(' ', '').replace(',', '.')
                                                if quantity.isdigit() and int(quantity) > 0:
                                                    try:
                                                        total_float = float(total)
                                                        qty_int = int(quantity)
                                                        price = str(total_float / qty_int)
                                                    except:
                                                        price = total
                                            
                                            item = {
                                                'number': '1',
                                                'name': name[:200],
                                                'quantity': quantity,
                                                'unit': unit,
                                                'price_without_vat': price,
                                                'total_with_vat': total,
                                                'amount_without_vat': total,
                                            }
                                            items.append(item)
                                            print(f"DEBUG items: Извлечен товар (fallback 2) #{item.get('number', 'N/A')}: {item.get('name', 'N/A')[:50]}, кол-во: {quantity}, ед: {unit}")
                                            skip_count = combined_line.count(' ') - line_clean.count(' ') + 1
                                            if skip_count > 1:
                                                i += skip_count - 1
                                            continue
                                else:
                                    name_part = combined_line[:fallback_match.start()].strip()
                                    name_part = re.sub(r'^\d+\s+', '', name_part)
                                    if len(name_part) >= 3:
                                        item = {
                                            'number': '1',
                                            'name': name_part[:200],
                                            'quantity': fallback_match.group(1).strip(),
                                            'unit': fallback_match.group(2).strip() if fallback_match.lastindex >= 2 else 'шт',
                                            'price_without_vat': fallback_match.group(3).replace(' ', '').replace(',', '.') if fallback_match.lastindex >= 3 else None,
                                            'total_with_vat': fallback_match.group(4).replace(' ', '').replace(',', '.') if fallback_match.lastindex >= 4 else None,
                                            'amount_without_vat': fallback_match.group(4).replace(' ', '').replace(',', '.') if fallback_match.lastindex >= 4 else None,
                                        }
                                        items.append(item)
                                        print(f"DEBUG items: Извлечен товар (fallback 1) #{item.get('number', 'N/A')}: {item.get('name', 'N/A')[:50]}")
                                        if combined_line != line_clean:
                                            i += 1
                                        continue
                            except Exception as e:
                                print(f"DEBUG items: Ошибка при fallback извлечении на строке {i}: {e}")
                                print(f"DEBUG items: Строка: {combined_line[:100]}")
                
                if not match and not re.search(r'^итого\s*$|^всего\s*$|итого\s+без\s+ндс|всего\s+с\s+ндс', line_clean, re.IGNORECASE):
                    desc_match = re.search(r'([А-Яа-яA-Za-z0-9\s,\.\-\(\)]{10,})', line_clean)
                    if desc_match:
                        desc = desc_match.group(1).strip()
                        if not re.match(r'^(итого|всего)', desc, re.IGNORECASE):
                            if len(desc) > 10:
                                amounts = re.findall(r'([\d\s]{3,}[,\.]\d{2})', line_clean)
                                if amounts:
                                    valid_amounts = [a for a in amounts if len(a.replace(' ', '').replace(',', '.').replace('.', '')) > 3]
                                    if valid_amounts:
                                        amount = valid_amounts[-1].replace(' ', '').replace(',', '.')
                                        price = valid_amounts[-2].replace(' ', '').replace(',', '.') if len(valid_amounts) >= 2 else amount
                                        
                                        price = re.sub(r'[^\d\.]+$', '', price)
                                        amount = re.sub(r'[^\d\.]+$', '', amount)
                                        
                                        items.append({
                                            'name': desc[:200],
                                            'price_without_vat': price,
                                            'total_with_vat': amount
                                        })
                                        print(f"DEBUG items: Извлечен товар (fallback): {desc[:50]}")
        
        if items:
            print(f"DEBUG items: Всего извлечено товаров: {len(items)}")
        else:
            print("DEBUG items: Товары не найдены")
        return items if items else None
    
    def _extract_vat(self, text: str) -> Optional[Dict]:
        """Возвращает ставку и сумму НДС, если найдены."""
        vat_patterns = [
            r'в\s+том\s+числе\s+ндс\s*(\d+)\s*%\s*[:\-]?\s*([\d\s,\.]{3,}[,\.]\d{2})',
            r'ндс\s*\(?(\d+)\s*%\)?\s*[:\-]?\s*([\d\s,\.]{3,}[,\.]\d{2})',
            r'НДС\s*(\d+)\s*%\s*[:\-]?\s*([\d\s,\.]{3,}[,\.]\d{2})',
            r'ндс\s*(\d+)\s*%\s*[:\-]?\s*([\d\s,\.]{3,}[,\.]\d{2})',
            r'в\s+том\s+числе\s+ндс\s*[:\-]?\s*([\d\s,\.]{3,}[,\.]\d{2})',
            r'(?:НДС|VAT|vat)\s*[:\-]?\s*([\d\s,\.]{3,}[,\.]\d{2})\s*(?:руб|RUB)',
            r'НДС\s*(\d+)\s*%\s*[:\-]?\s*([\d\s,\.]+)',
            r'VAT\s*(\d+)\s*%\s*[:\-]?\s*([\d\s,\.]+)',
        ]
        
        for pattern in vat_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                rate = match.group(1) if match.lastindex >= 1 and match.group(1).isdigit() else None
                amount = match.group(2).strip() if match.lastindex >= 2 else (match.group(1).strip() if match.lastindex >= 1 else None)
                if amount:
                    if not rate:
                        rate_match = re.search(r'(\d+)\s*%', text[:match.start()] if match.start() else text, re.IGNORECASE)
                        rate = rate_match.group(1) if rate_match else None
                    
                    return {
                        'rate': rate or '20',
                        'amount': amount
                    }
        
        return None
    
    def _extract_currency(self, text: str) -> Optional[str]:
        """Определяет валюту (RUB/USD/EUR) по тексту."""
        currency_patterns = [
            r'([A-Z]{3})\s*(?:руб|RUB|USD|EUR)',
            r'(?:руб|RUB|₽)',
            r'(?:USD|\$)',
            r'(?:EUR|€)',
        ]
        
        for pattern in currency_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                currency = match.group(1) if match.lastindex else match.group(0)
                if currency:
                    return currency.upper()
                elif 'руб' in match.group(0).lower() or 'rub' in match.group(0).lower():
                    return 'RUB'
                elif 'usd' in match.group(0).lower() or '$' in match.group(0):
                    return 'USD'
                elif 'eur' in match.group(0).lower() or '€' in match.group(0):
                    return 'EUR'
        
        return 'RUB'
    
    def _extract_payment_terms(self, text: str) -> Optional[str]:
        """Извлекает срок оплаты (например, '10 дней')."""
        terms_patterns = [
            r'(?:срок\s*оплаты|payment\s*terms|срок)\s*[:\-]?\s*(\d+\s*(?:дней|days|день))',
            r'(?:оплата|payment)\s*в\s*течение\s*(\d+\s*(?:дней|days|день))',
        ]
        
        for pattern in terms_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        return None
    
    def _extract_seller_inn(self, text: str) -> Optional[str]:
        """Возвращает ИНН продавца (раздел 'Поставщик')."""
        patterns = [
            r'поставщик[^п]*?ИНН\s*[:\-]?\s*(\d{10,12})(?![^п]*покупатель)',
            r'исполнитель[^п]*?ИНН\s*[:\-]?\s*(\d{10,12})(?![^п]*покупатель)',
            r'продавец[^п]*?ИНН\s*[:\-]?\s*(\d{10,12})(?![^п]*покупатель)',
            r'поставщик[^п]*?[:\-]?[^\d]*ИНН\s*[:\-]?\s*(\d{10,12})(?![^п]*покупатель)',
            r'исполнитель[^п]*?[:\-]?[^\d]*ИНН\s*[:\-]?\s*(\d{10,12})(?![^п]*покупатель)',
            r'продавец[^п]*?[:\-]?[^\d]*ИНН\s*[:\-]?\s*(\d{10,12})(?![^п]*покупатель)',
        ]
        
        for pattern_idx, pattern in enumerate(patterns):
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                inn = match.group(1).strip()
                print(f"DEBUG seller_inn: Паттерн #{pattern_idx} нашел ИНН: {inn}")
                return inn
        
        print("DEBUG seller_inn: ИНН не найден")
        return None
    
    def _extract_seller_kpp(self, text: str) -> Optional[str]:
        """Возвращает КПП продавца (раздел 'Поставщик')."""
        patterns = [
            r'поставщик.*?КПП\s*(\d{9})(?!.*покупатель)',
            r'исполнитель.*?КПП\s*(\d{9})(?!.*покупатель)',
            r'продавец.*?КПП\s*(\d{9})(?!.*покупатель)',
            r'поставщик.*?ИНН\s*\d{10,12}.*?КПП\s*(\d{9})(?!.*покупатель)',
            r'исполнитель.*?ИНН\s*\d{10,12}.*?КПП\s*(\d{9})(?!.*покупатель)',
            r'продавец.*?ИНН\s*\d{10,12}.*?КПП\s*(\d{9})(?!.*покупатель)',
            r'поставщик[^п]*?КПП\s*[:\-]?\s*(\d{9})(?![^п]*покупатель)',
            r'исполнитель[^п]*?КПП\s*[:\-]?\s*(\d{9})(?![^п]*покупатель)',
            r'продавец[^п]*?КПП\s*[:\-]?\s*(\d{9})(?![^п]*покупатель)',
        ]
        
        for pattern_idx, pattern in enumerate(patterns):
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                kpp = match.group(1).strip()
                print(f"DEBUG seller_kpp: Паттерн #{pattern_idx} нашел КПП: {kpp}")
                return kpp
        
        print("DEBUG seller_kpp: КПП не найден")
        return None
    
    def _extract_buyer_inn(self, text: str) -> Optional[str]:
        """Возвращает ИНН покупателя (раздел 'Покупатель')."""
        patterns = [
            r'покупатель[^:]*[:\-]?[^\d]*ИНН\s*[:\-]?\s*(\d{10,12})',
            r'заказчик[^:]*[:\-]?[^\d]*ИНН\s*[:\-]?\s*(\d{10,12})',
            r'клиент[^:]*[:\-]?[^\d]*ИНН\s*[:\-]?\s*(\d{10,12})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                return match.group(1).strip()
        
        return None
    
    def _extract_buyer_kpp(self, text: str) -> Optional[str]:
        """Возвращает КПП покупателя (раздел 'Покупатель')."""
        patterns = [
            r'покупатель[^:]*[:\-]?[^\d]*КПП\s*[:\-]?\s*(\d{9})',
            r'заказчик[^:]*[:\-]?[^\d]*КПП\s*[:\-]?\s*(\d{9})',
            r'клиент[^:]*[:\-]?[^\d]*КПП\s*[:\-]?\s*(\d{9})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                return match.group(1).strip()
        
        return None
    
    def _extract_seller_address(self, text: str) -> Optional[str]:
        """Извлекает адрес продавца из блока 'Поставщик'."""
        patterns = [
            r'поставщик.*?адрес[^:]*?[:\-]?\s*([^\n]{10,200}?)(?=\s*(?:ИНН|КПП|Тел|Телефон|Покупатель|р/с|к/с|$))',
            r'поставщик.*?КПП\s*\d{9}.*?\n\s*([0-9]{5,6}[^\n]{10,200}?)(?=\s*(?:Тел|Телефон|р/с|к/с|Покупатель|$))',
            r'поставщик.*?ИНН\s*\d{10,12}.*?КПП\s*\d{9}.*?\n\s*([0-9]{5,6}[^\n]{10,200}?)(?=\s*(?:Тел|Телефон|р/с|к/с|Покупатель|$))',
            r'поставщик.*?КПП\s*\d{9}\s+([0-9]{5,6}[^\n]{10,200}?)(?=\s*(?:Тел|Телефон|р/с|к/с|Покупатель|$))',
            r'поставщик.*?КПП\s*\d{9}.*?([0-9]{5,6}[^\n]{10,200}?)(?=\s*(?:Тел|Телефон|р/с|к/с|Покупатель|$))',
            r'поставщик.*?КПП\s*\d{9}(.*?)(?=покупатель|$)',
        ]
        
        for pattern_idx, pattern in enumerate(patterns):
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
            if match:
                address = match.group(1).strip()
                address = re.sub(r'\s+', ' ', address)
                address = re.sub(r'\n+', ' ', address)
                if pattern_idx == len(patterns) - 1:
                    address_match = re.search(r'([0-9]{5,6}[^\n]{10,200}?)(?=\s*(?:Тел|Телефон|р/с|к/с|Покупатель|$))', address, re.IGNORECASE)
                    if address_match:
                        address = address_match.group(1).strip()
                    else:
                        address_match = re.search(r'([0-9]{5,6}.*?(?:область|обл|город|г\.|ул\.|улица|д\.|дом|офис|помещ).{10,200}?)(?=\s*(?:Тел|Телефон|р/с|к/с|Покупатель|$))', address, re.IGNORECASE)
                        if address_match:
                            address = address_match.group(1).strip()
                        else:
                            continue
                if len(address) > 10:
                    print(f"DEBUG seller_address: Паттерн #{pattern_idx} нашел адрес: {address[:50]}...")
                    return address
        
        print("DEBUG seller_address: Адрес не найден")
        return None
    
    def _extract_seller_phone(self, text: str, buyer_phone: Optional[str] = None) -> Optional[str]:
        """
        Извлекает телефон продавца (в секции "Поставщик")
        """
        buyer_keyword_pos = text.lower().find('покупатель')
        if buyer_keyword_pos == -1:
            buyer_keyword_pos = len(text)
        
        patterns = [
            r'поставщик.*?тел[^:]*?[:\-]?\s*([+\d\s\-\(\)]{7,20})(?!.*покупатель)',
            r'поставщик.*?телефон[^:]*?[:\-]?\s*([+\d\s\-\(\)]{7,20})(?!.*покупатель)',
            r'поставщик.*?КПП\s*\d{9}.*?([0-9]{5,6}.*?)([8]\d{10})(?!.*покупатель)',
            r'поставщик.*?[0-9]{5,6}.*?([8]\d{10})(?!.*покупатель)',
        ]
        
        for pattern_idx, pattern in enumerate(patterns):
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
            if match:
                if match.lastindex >= 2:
                    phone = match.group(2).strip()
                else:
                    phone = match.group(1).strip()
                phone = re.sub(r'\s+', '', phone)
                if phone.startswith('8') and len(phone) == 11:
                    phone_start_pos = match.start()
                    if phone_start_pos > buyer_keyword_pos:
                        print(f"DEBUG seller_phone: Паттерн #{pattern_idx} нашел телефон после слова 'покупатель', пропускаем: {phone}")
                        continue
                    
                    if buyer_phone and phone == buyer_phone:
                        print(f"DEBUG seller_phone: Паттерн #{pattern_idx} нашел телефон покупателя (совпадает с buyer_phone), пропускаем: {phone}")
                        continue
                    
                    seller_keyword_pos = text.lower().find('поставщик')
                    if seller_keyword_pos != -1 and phone_start_pos > seller_keyword_pos + 500:
                        print(f"DEBUG seller_phone: Паттерн #{pattern_idx} нашел телефон слишком далеко от 'поставщик', пропускаем: {phone}")
                        continue
                    
                    print(f"DEBUG seller_phone: Паттерн #{pattern_idx} нашел телефон: {phone}")
                    return phone
        
        print("DEBUG seller_phone: Телефон не найден")
        return None
    
    def _extract_buyer_address(self, text: str) -> Optional[str]:
        """Извлекает адрес покупателя из блока 'Покупатель'."""
        patterns = [
            r'покупатель[^:]*?адрес[^:]*?[:\-]?\s*([^\n]{10,200}?)(?=\s*(?:ИНН|КПП|Тел|Телефон|$))',
            r'покупатель[^:]*?[:\-]?\s*[^\n]*?ИНН[^\n]*?КПП[^\n]*?([0-9]{5,6}[^\n]{10,150}?)(?=\s*(?:Тел|Телефон|$))',
            r'покупатель[^:]*?[:\-]?\s*[^\n]*?КПП[^\n]*?([0-9]{5,6}[^\n]{10,150}?)(?=\s*(?:Тел|Телефон|$))',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
            if match:
                address = match.group(1).strip()
                address = re.sub(r'\s+', ' ', address)
                if len(address) > 10:
                    return address
        
        return None
    
    def _extract_buyer_phone(self, text: str) -> Optional[str]:
        """Возвращает телефон покупателя из блока 'Покупатель'."""
        patterns = [
            r'покупатель[^:]*?тел[^:]*?[:\-]?\s*([+\d\s\-\(\)]{7,20})',
            r'покупатель[^:]*?телефон[^:]*?[:\-]?\s*([+\d\s\-\(\)]{7,20})',
            r'покупатель[^:]*?[:\-]?\s*[^\n]*?([8]\s*[\(\-]?\s*\d{3}\s*[\)\-]?\s*\d{3}[\s\-]?\d{2}[\s\-]?\d{2})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                phone = match.group(1).strip()
                phone = re.sub(r'\s+', ' ', phone)
                return phone
        
        return None
    
    def _build_invoice_section(self, text: str, invoice_number: Optional[str], invoice_date: Optional[str]) -> Dict:
        """Собирает секцию invoice (номер, дата, заголовок, срок действия)."""
        invoice = {}
        if invoice_number:
            invoice['number'] = invoice_number
        if invoice_date:
            invoice['date'] = invoice_date
        
        validity_match = re.search(r'действителен\s+в\s+течение\s+(\d+\s+банковских?\s+дней?)', text, re.IGNORECASE)
        if validity_match:
            invoice['validity_period'] = validity_match.group(1)
        
        title_match = re.search(r'(СЧЁТ\s*№\s*[\d/]+\s+от\s+[\d\.]+)', text, re.IGNORECASE)
        if title_match:
            invoice['title'] = title_match.group(1)
        
        return invoice if invoice else None
    
    def _build_supplier_section(self, text: str, seller_name: Optional[str], buyer_phone: Optional[str]) -> Dict:
        """Собирает секцию supplier (название, ИНН/КПП, адрес, телефон, банк.реквизиты)."""
        supplier = {}
        
        if seller_name:
            supplier['company_name'] = seller_name
        
        seller_inn = self._extract_seller_inn(text)
        if seller_inn:
            supplier['inn'] = seller_inn
        
        seller_kpp = self._extract_seller_kpp(text)
        if seller_kpp:
            supplier['kpp'] = seller_kpp
        
        seller_address = self._extract_seller_address(text)
        if seller_address:
            supplier['address'] = seller_address
        
        seller_phone = self._extract_seller_phone(text, buyer_phone)
        if seller_phone:
            supplier['phone'] = seller_phone
        
        bank_details = self._extract_bank_details(text)
        if bank_details:
            supplier['bank_details'] = bank_details
        
        return supplier if supplier else None
    
    def _build_customer_section(self, text: str, buyer_name: Optional[str], buyer_phone: Optional[str]) -> Dict:
        """Собирает секцию customer (название, ИНН/КПП, адрес, телефон, договор)."""
        customer = {}
        
        if buyer_name:
            customer['company_name'] = buyer_name
        
        buyer_inn = self._extract_buyer_inn(text)
        if buyer_inn:
            customer['inn'] = buyer_inn
        
        buyer_kpp = self._extract_buyer_kpp(text)
        if buyer_kpp:
            customer['kpp'] = buyer_kpp
        
        buyer_address = self._extract_buyer_address(text)
        if buyer_address:
            customer['address'] = buyer_address
        
        if buyer_phone:
            customer['phone'] = buyer_phone
        
        contract = self._extract_contract(text)
        if contract:
            customer['contract'] = contract
        else:
            customer['contract'] = {'number': None, 'date': None}
        
        return customer if customer else None
    
    def _extract_line_items_structured(self, text: str, tables: Optional[List] = None) -> List[Dict]:
        """Возвращает список товарных позиций в структурированном виде."""
        items = self._extract_items(text)
        if not items:
            return []
        
        line_items = []
        for idx, item in enumerate(items, 1):
            line_item = {
                'line_number': int(item.get('number', idx)) if item.get('number', '').isdigit() else idx,
                'product_name': item.get('name', ''),
            }
            
            if item.get('unit'):
                line_item['unit'] = item['unit']
            if item.get('quantity'):
                line_item['quantity'] = self._clean_number(item['quantity'])
            if item.get('delivery_terms'):
                line_item['delivery_terms'] = item['delivery_terms']
            if item.get('price_without_vat'):
                line_item['unit_price_without_vat'] = self._clean_number(item['price_without_vat'])
            if item.get('amount_without_vat'):
                line_item['amount_without_vat'] = self._clean_number(item['amount_without_vat'])
            if item.get('vat_amount'):
                line_item['vat_amount'] = self._clean_number(item['vat_amount'])
            if item.get('total_with_vat'):
                line_item['total_with_vat'] = self._clean_number(item['total_with_vat'])
            
            line_items.append(line_item)
        
        return line_items
    
    def _build_financial_summary(self, text: str) -> Dict:
        """Собирает финсводку: subtotal, ставка/сумма НДС, итого, прописью, валюта."""
        summary = {}
        
        total_match = re.search(r'итого\s+без\s+ндс[^\d]*?([\d\s,\.]{3,}[,\.]\d{2})', text, re.IGNORECASE)
        if total_match:
            summary['subtotal_without_vat'] = self._clean_number(total_match.group(1))
        
        vat_info = self._extract_vat(text)
        if vat_info:
            if isinstance(vat_info, dict):
                summary['vat_rate'] = f"{vat_info.get('rate', '20')}%"
                summary['vat_amount'] = self._clean_number(vat_info.get('amount', '0'))
            else:
                summary['vat_rate'] = "20%"
                summary['vat_amount'] = self._clean_number(str(vat_info))
        
        total_with_vat_match = re.search(r'всего\s+с\s+ндс[^\d]*?([\d\s,\.]{3,}[,\.]\d{2})', text, re.IGNORECASE)
        if total_with_vat_match:
            summary['total_with_vat'] = self._clean_number(total_with_vat_match.group(1))
        else:
            total_match = self._extract_field(text, 'total_amount')
            if total_match:
                summary['total_with_vat'] = self._clean_number(total_match)
        
        total_in_words = self._extract_total_in_words(text)
        if total_in_words:
            summary['total_in_words'] = total_in_words
        
        currency = self._extract_currency(text)
        if currency:
            summary['currency'] = currency.upper()
        else:
            summary['currency'] = 'RUB'
        
        return summary if summary else None
    
    def _extract_signatories(self, text: str) -> Dict:
        """Находит подписантов (директор по продажам, главный бухгалтер, выписал)."""
        signatories = {}
        
        sales_dir_match = re.search(r'директор\s+по\s+продажам[^\n]*?([А-ЯЁ][а-яё]+\s+[А-ЯЁ]\.\s*[А-ЯЁ]\.)', text, re.IGNORECASE)
        if sales_dir_match:
            signatories['sales_director'] = sales_dir_match.group(1)
        
        accountant_match = re.search(r'главный\s+бухгалтер[^\n]*?([А-ЯЁ][а-яё]+\s+[А-ЯЁ]\.\s*[А-ЯЁ]\.)', text, re.IGNORECASE)
        if accountant_match:
            signatories['chief_accountant'] = accountant_match.group(1)
        
        issued_match = re.search(r'выписал[^\n]*?([А-ЯЁ][а-яё]+\s+[А-ЯЁ]\.\s*[А-ЯЁ]\.)', text, re.IGNORECASE)
        if issued_match:
            signatories['issued_by'] = issued_match.group(1)
        
        return signatories if signatories else None
    
    def _extract_terms_and_conditions(self, text: str) -> List[Dict]:
        """Извлекает нумерованные условия/положения документа."""
        terms = []
        
        pattern = r'(\d+)\.\s+([^\n]{20,500}?)(?=\d+\.|$)'
        matches = re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
        
        for match in matches:
            number = match.group(1)
            text_content = match.group(2).strip()
            text_content = re.sub(r'\s+', ' ', text_content)
            if len(text_content) > 20:
                terms.append({
                    'number': int(number),
                    'text': text_content
                })
        
        return terms if terms else None
    
    def _extract_additional_info(self, text: str) -> Dict:
        """Ищет дополнительную информацию (самовывоз: адрес, контакт, телефон)."""
        info = {}
        
        pickup_match = re.search(r'самовывоз[^\n]*?([А-Яа-я\s,\.\d]{20,150})', text, re.IGNORECASE)
        if pickup_match:
            info['pickup_address'] = pickup_match.group(1).strip()
        
        pickup_contact_match = re.search(r'контактным\s+лицом[^\n]*?([А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+)', text, re.IGNORECASE)
        if pickup_contact_match:
            info['pickup_contact'] = pickup_contact_match.group(1)
        
        pickup_phone_match = re.search(r'тел\.\s*([8]\d{10})', text, re.IGNORECASE)
        if pickup_phone_match:
            info['pickup_phone'] = pickup_phone_match.group(1)
        
        return info if info else None
    
    def _extract_bank_details(self, text: str) -> Optional[Dict]:
        """Извлекает банковские реквизиты поставщика (р/с, к/с, БИК, банк)."""
        bank_details = {}
        
        account_match = re.search(r'р/с\s*[:\-]?\s*(\d{20})', text, re.IGNORECASE)
        if account_match:
            bank_details['account'] = account_match.group(1)
        
        corr_account_match = re.search(r'к/с\s*[:\-]?\s*(\d{20})', text, re.IGNORECASE)
        if corr_account_match:
            bank_details['correspondent_account'] = corr_account_match.group(1)
        
        bik_match = re.search(r'БИК\s*[:\-]?\s*(\d{9})', text, re.IGNORECASE)
        if bik_match:
            bank_details['bik'] = bik_match.group(1)
        
        bank_name_match = re.search(r'в\s+([А-Яа-я\s\"\(\)]+(?:Банк|Банка|ПАО|АО)[А-Яа-я\s\"\(\)]*)', text, re.IGNORECASE)
        if bank_name_match:
            bank_details['bank_name'] = bank_name_match.group(1).strip()
        
        return bank_details if bank_details else None
    
    def _extract_contract(self, text: str) -> Optional[Dict]:
        """Возвращает номер и дату договора, если найдены."""
        contract = {}
        
        contract_num_match = re.search(r'договор[^\n]*?№\s*([\d/\-]+)', text, re.IGNORECASE)
        if contract_num_match:
            contract['number'] = contract_num_match.group(1)
        
        contract_date_match = re.search(r'договор[^\n]*?от\s*(\d{2}\.\d{2}\.\d{4})', text, re.IGNORECASE)
        if contract_date_match:
            contract['date'] = contract_date_match.group(1)
        
        return contract if contract else None
    
    def _extract_total_in_words(self, text: str) -> Optional[str]:
        """Находит сумму прописью (рубли/копейки)."""
        pattern = r'([А-Яа-я\s]+тысяч[а-я]*\s+[А-Яа-я\s]+рубл[а-я]+\s+\d+\s+копеек)'
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        
        pattern2 = r'([А-Яа-я\s]+рубл[а-я]+\s+\d+\s+копеек)'
        match2 = re.search(pattern2, text, re.IGNORECASE)
        if match2:
            return match2.group(1).strip()
        
        return None
    
    def _clean_number(self, value: str) -> float:
        """Парсит число из строки (убирает пробелы/кавычки, заменяет запятую)."""
        if not value:
            return 0.0
        
        value_str = str(value).replace(' ', '').replace('"', '').replace(',', '.')
        try:
            return float(value_str)
        except ValueError:
            return 0.0
    
    def _clean_result(self, result: Dict) -> Dict:
        """Удаляет пустые словари/списки/None из результата."""
        cleaned = {}
        for key, value in result.items():
            if value is None:
                continue
            if isinstance(value, dict) and not value:
                continue
            if isinstance(value, list) and not value:
                continue
            cleaned[key] = value
        return cleaned
