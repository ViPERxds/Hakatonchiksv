"""
ML модель для классификации и валидации полей в счетах
"""
import re
import pickle
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
import pandas as pd


class InvoiceFieldClassifier:
    """
    ML модель для классификации строк текста по типам полей счета
    """
    
    FIELD_TYPES = [
        'invoice_number',
        'date',
        'seller',
        'buyer',
        'inn',
        'kpp',
        'total_amount',
        'vat',
        'item',
        'other'
    ]
    
    def __init__(self):
        self.vectorizer = TfidfVectorizer(
            max_features=1000,
            ngram_range=(1, 3),
            analyzer='char_wb',  # Используем символьные n-граммы для работы с русским текстом
            min_df=1,
            max_df=0.95
        )
        self.classifier = RandomForestClassifier(
            n_estimators=100,
            max_depth=20,
            random_state=42,
            n_jobs=-1
        )
        self.is_trained = False
    
    def extract_features(self, text: str) -> Dict:
        """
        Извлекает признаки из текста для классификации
        """
        text_lower = text.lower()
        
        features = {
            'has_invoice_number': bool(re.search(r'[№#]\s*\d+', text, re.IGNORECASE)),
            'has_date': bool(re.search(r'\d{1,2}[./-]\d{1,2}[./-]\d{2,4}', text)),
            'has_inn': bool(re.search(r'инн\s*\d{10,12}', text, re.IGNORECASE)),
            'has_kpp': bool(re.search(r'кпп\s*\d{9}', text, re.IGNORECASE)),
            'has_company': bool(re.search(r'(ооо|ип|llc|company)', text, re.IGNORECASE)),
            'has_amount': bool(re.search(r'[\d\s]{3,}[,\.]\d{2}', text)),
            'has_vat': bool(re.search(r'ндс|vat', text, re.IGNORECASE)),
            'has_seller_keywords': bool(re.search(r'(поставщик|исполнитель|продавец|отправитель)', text, re.IGNORECASE)),
            'has_buyer_keywords': bool(re.search(r'(покупатель|заказчик|клиент|получатель)', text, re.IGNORECASE)),
            'text_length': len(text),
            'digit_count': len(re.findall(r'\d', text)),
            'word_count': len(text.split()),
            'has_currency': bool(re.search(r'(руб|rub|usd|eur|₽|\$|€)', text, re.IGNORECASE)),
        }
        return features
    
    def prepare_training_data(self, texts: List[str], labels: List[str]) -> Tuple:
        """
        Подготавливает данные для обучения
        """
        # Извлекаем признаки
        feature_dicts = [self.extract_features(text) for text in texts]
        feature_df = pd.DataFrame(feature_dicts)
        
        # Векторизуем текст
        text_vectors = self.vectorizer.fit_transform(texts)
        
        # Преобразуем признаки в числовой формат (float)
        # Убеждаемся, что все значения числовые
        feature_array = feature_df.astype(float).values
        
        # Преобразуем в разреженную матрицу для объединения
        from scipy.sparse import hstack, csr_matrix
        feature_sparse = csr_matrix(feature_array)
        
        # Объединяем признаки
        X = hstack([text_vectors, feature_sparse])
        
        # Преобразуем метки в числовые
        label_to_idx = {label: idx for idx, label in enumerate(self.FIELD_TYPES)}
        y = np.array([label_to_idx[label] for label in labels])
        
        return X, y
    
    def train(self, texts: List[str], labels: List[str], test_size: float = 0.2) -> Dict:
        """
        Обучает модель на предоставленных данных
        """
        if len(texts) != len(labels):
            raise ValueError("Количество текстов и меток должно совпадать")
        
        X, y = self.prepare_training_data(texts, labels)
        
        # Разделяем на обучающую и тестовую выборки
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=42, stratify=y
        )
        
        # Обучаем модель
        self.classifier.fit(X_train, y_train)
        self.is_trained = True
        
        # Оцениваем качество
        y_pred = self.classifier.predict(X_test)
        accuracy = accuracy_score(y_test, y_pred)
        
        # Детальный отчет
        idx_to_label = {idx: label for label, idx in enumerate(self.FIELD_TYPES)}
        y_test_labels = [self.FIELD_TYPES[y] for y in y_test]
        y_pred_labels = [self.FIELD_TYPES[y] for y in y_pred]
        
        # Используем zero_division=0 для подавления предупреждений
        report = classification_report(
            y_test_labels, y_pred_labels, 
            labels=self.FIELD_TYPES,
            output_dict=True,
            zero_division=0
        )
        cm = confusion_matrix(y_test_labels, y_pred_labels, labels=self.FIELD_TYPES)
        
        return {
            'accuracy': accuracy,
            'classification_report': report,
            'confusion_matrix': cm.tolist(),
            'train_size': X_train.shape[0],
            'test_size': X_test.shape[0]
        }
    
    def predict(self, text: str) -> Tuple[str, float]:
        """
        Предсказывает тип поля для текста
        Возвращает (тип_поля, уверенность)
        """
        if not self.is_trained:
            raise ValueError("Модель не обучена. Сначала вызовите train()")
        
        # Извлекаем признаки
        features = self.extract_features(text)
        feature_df = pd.DataFrame([features])
        
        # Векторизуем текст
        text_vector = self.vectorizer.transform([text])
        
        # Преобразуем признаки в числовой формат и разреженную матрицу
        from scipy.sparse import hstack, csr_matrix
        feature_array = feature_df.astype(float).values
        feature_sparse = csr_matrix(feature_array)
        
        # Объединяем признаки
        X = hstack([text_vector, feature_sparse])
        
        # Предсказываем
        prediction = self.classifier.predict(X)[0]
        probabilities = self.classifier.predict_proba(X)[0]
        confidence = probabilities[prediction]
        
        field_type = self.FIELD_TYPES[prediction]
        return field_type, confidence
    
    def validate_extraction(self, field_type: str, extracted_value: str, context: str = "") -> Tuple[bool, float]:
        """
        Валидирует извлеченное значение с помощью ML
        """
        if not self.is_trained:
            # Если модель не обучена, возвращаем базовую валидацию
            return self._basic_validation(field_type, extracted_value)
        
        # Используем контекст для валидации
        validation_text = f"{context} {extracted_value}" if context else extracted_value
        predicted_type, confidence = self.predict(validation_text)
        
        # Проверяем, соответствует ли предсказанный тип ожидаемому
        is_valid = predicted_type == field_type or predicted_type == 'other'
        return is_valid, confidence
    
    def _basic_validation(self, field_type: str, value: str) -> Tuple[bool, float]:
        """
        Базовая валидация без ML
        """
        if not value:
            return False, 0.0
        
        validations = {
            'invoice_number': bool(re.match(r'^\d{1,10}$', value)),
            'date': bool(re.search(r'\d{1,2}[./-]\d{1,2}[./-]\d{2,4}', value)),
            'inn': bool(re.match(r'^\d{10,12}$', value)),
            'kpp': bool(re.match(r'^\d{9}$', value)),
            'total_amount': bool(re.search(r'[\d\s,\.]+', value)),
        }
        
        is_valid = validations.get(field_type, True)
        confidence = 0.8 if is_valid else 0.3
        return is_valid, confidence
    
    def save(self, filepath: str):
        """
        Сохраняет модель в файл
        """
        model_data = {
            'vectorizer': self.vectorizer,
            'classifier': self.classifier,
            'is_trained': self.is_trained
        }
        
        with open(filepath, 'wb') as f:
            pickle.dump(model_data, f)
    
    def load(self, filepath: str):
        """
        Загружает модель из файла
        """
        if not Path(filepath).exists():
            raise FileNotFoundError(f"Файл модели не найден: {filepath}")
        
        with open(filepath, 'rb') as f:
            model_data = pickle.load(f)
        
        self.vectorizer = model_data['vectorizer']
        self.classifier = model_data['classifier']
        self.is_trained = model_data['is_trained']


def create_sample_training_data() -> Tuple[List[str], List[str]]:
    """
    Создает примерные данные для обучения модели на основе реальных форматов счетов
    """
    texts = []
    labels = []
    
    # Номера счетов (реальные форматы)
    texts.extend([
        "СЧЁТ № 2/168935",
        "Счет на оплату № 650",
        "Счет на оплату № 315",
        "Счет-оферта 6765712",
        "Счет-фактура № 111",
        "Счет № 12345 от 15.09.2025",
        "Invoice #67890",
        "№ 999",
        "Счет № 2/168935 от 16.09.2025",
    ])
    labels.extend(['invoice_number'] * 9)
    
    # Даты (реальные форматы)
    texts.extend([
        "от 16.09.2025",
        "от 15 сентября 2025 г.",
        "от 15.09.2025",
        "Дата: 20.03.2024",
        "Date: 01/15/2024",
        "15.01.2024",
        "от 11/09/2025",
        "16.09.2025",
    ])
    labels.extend(['date'] * 8)
    
    # Поставщики (реальные форматы)
    texts.extend([
        "Поставщик: ООО ТД \"Промэлектроника\"",
        "ООО \"Элитан Трейд\"",
        "ООО \"НОВЫЕ ТЕХНОЛОГИИ\"",
        "ИП Малафеев Николай Михайлович",
        "Поставщик (Исполнитель): ООО \"Компания\"",
        "Исполнитель ООО \"ВАСИЛЕК\"",
        "Продавец: ИП Иванов Иван Иванович",
        "Отправитель: ООО Технологии",
    ])
    labels.extend(['seller'] * 8)
    
    # Покупатели (реальные форматы)
    texts.extend([
        "Покупатель: ООО \"ИТ\"",
        "Покупатель (Заказчик): АО \"МК \"ВЫСОТА\"",
        "АО \"МК \"ВЫСОТА\"",
        "Покупатель: ООО \"Клиент\"",
        "Заказчик ИП Петров",
        "Клиент: ООО \"Партнер\"",
        "Получатель: Владислав С.",
        "Покупатель ООО \"Заказчик\"",
    ])
    labels.extend(['buyer'] * 8)
    
    # ИНН
    texts.extend([
        "ИНН: 1234567890",
        "ИНН 9876543210",
        "INN: 1122334455",
        "Поставщик ИНН: 1234567890",
        "ИНН 123456789012",
    ])
    labels.extend(['inn'] * 5)
    
    # КПП
    texts.extend([
        "КПП: 123456789",
        "КПП 987654321",
        "KPP: 123456789",
        "Поставщик КПП: 123456789",
        "КПП 111222333",
    ])
    labels.extend(['kpp'] * 5)
    
    # Суммы (реальные форматы)
    texts.extend([
        "Итого: 243 375,00",
        "Всего к оплате: 292 050,00",
        "Всего с НДС: 191,468.22",
        "К оплате: 83 000,00 руб.",
        "Всего к оплате: 1 659 649,00",
        "Итого: 2 500 000,00",
        "Сумма: 1 234 567,89",
        "Total: 999.99",
        "Всего наименований 1, на сумму 83 000,00 руб.",
    ])
    labels.extend(['total_amount'] * 9)
    
    # НДС (реальные форматы)
    texts.extend([
        "НДС (20%): 48 675,00",
        "В том числе НДС 20%: 13 833,33",
        "НДС 20%: 66 720,35",
        "в том числе НДС 20%: 31 911,37 руб.",
        "НДС: 10000.00 руб.",
        "VAT 18%: 5000.00",
        "ндс 20% 20000.00",
        "НДС 10%: 1000,00",
    ])
    labels.extend(['vat'] * 8)
    
    # Товары (реальные форматы из таблиц)
    texts.extend([
        "Контрактное производство товара SLS_Gateway",
        "Механическая рамка для трафаретов, двухсторонняя, Модель НТ-M-430",
        "Электроэлемент 0805W8F680JT5E@ROYALOHM",
        "Электроэлемент ESP32-WROVER-IB(16MB)@ESPRESSYST",
        "Полуавтоматическая машина для шелкографии с плоской кроватью YX3250",
        "1. Услуга консультации - 1 шт. - 10000.00 руб.",
        "Разработка ПО - 1 шт. - 50000.00 руб.",
        "Товар: Оборудование - 2 шт. - 15000.00",
        "Оформление дубликата Счета-оферты на бумажном носителе",
    ])
    labels.extend(['item'] * 9)
    
    # Другое
    texts.extend([
        "Адрес: г. Москва, ул. Примерная, д. 1",
        "Телефон: +7 (999) 123-45-67",
        "Email: info@example.com",
        "Банковские реквизиты",
        "Примечание: Оплата в течение 10 дней",
    ])
    labels.extend(['other'] * 5)
    
    return texts, labels

