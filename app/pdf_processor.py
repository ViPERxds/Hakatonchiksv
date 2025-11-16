import pdfplumber
import PyPDF2
import pytesseract
from pdf2image import convert_from_path
from PIL import Image
import io
import cv2
import numpy as np
from typing import Optional, List, Dict, Any


class PDFProcessor:
    """Утилиты для извлечения текста/таблиц/изображений из PDF и картинок"""
    
    def __init__(self):
        self.use_ocr = True
    
    def extract_text(self, pdf_path: str) -> str:
        """Возвращает текст из PDF. Для сканов автоматически включает OCR."""
        try:
            full_text = []
            total_text_length = 0
            
            # Сначала пробуем pdfplumber (текстовый PDF)
            try:
                with pdfplumber.open(pdf_path) as pdf:
                    for page_num, page in enumerate(pdf.pages, 1):
                        text = page.extract_text()
                        # Если текста мало — вероятно, скан: переключаемся на OCR для страницы
                        if text and len(text.strip()) > 50:
                            full_text.append(f"--- Страница {page_num} ---\n{text}\n")
                            total_text_length += len(text.strip())
                        else:
                            print(f"Текста на странице {page_num} недостаточно, используем OCR...")
                            text = self._extract_text_with_ocr_from_page(pdf_path, page_num)
                            if text:
                                full_text.append(f"--- Страница {page_num} ---\n{text}\n")
                                total_text_length += len(text.strip())
                
                result = "\n".join(full_text)
                if result.strip() and total_text_length > 100:
                    return result
                else:
                    print("Текст слишком короткий, пробуем полный OCR...")
            except Exception as e:
                print(f"pdfplumber не смог обработать: {str(e)}")
            
            # Если pdfplumber не помог — пробуем PyPDF2
            try:
                full_text = []
                total_text_length = 0
                with open(pdf_path, 'rb') as file:
                    pdf_reader = PyPDF2.PdfReader(file)
                    for page_num, page in enumerate(pdf_reader.pages, 1):
                        text = page.extract_text()
                        if text and len(text.strip()) > 50:
                            full_text.append(f"--- Страница {page_num} ---\n{text}\n")
                            total_text_length += len(text.strip())
                        else:
                            print(f"Текста на странице {page_num} недостаточно, используем OCR...")
                            text = self._extract_text_with_ocr_from_page(pdf_path, page_num)
                            if text:
                                full_text.append(f"--- Страница {page_num} ---\n{text}\n")
                                total_text_length += len(text.strip())
                
                result = "\n".join(full_text)
                if result.strip() and total_text_length > 100:
                    return result
                else:
                    print("Текст слишком короткий, пробуем полный OCR...")
            except Exception as e:
                print(f"PyPDF2 не смог обработать: {str(e)}")
            
            # В крайнем случае — полный OCR по всему документу
            print("Используем полный OCR для всего документа...")
            return self._extract_text_with_ocr_full(pdf_path)
        
        except Exception as e:
            raise Exception(f"Ошибка обработки PDF: {str(e)}")
    
    def _extract_text_with_ocr_from_page(self, pdf_path: str, page_num: int) -> str:
        """OCR одной страницы PDF."""
        try:
            images = convert_from_path(pdf_path, first_page=page_num, last_page=page_num, dpi=300)
            
            if not images:
                return ""
            
            img = images[0]
            img_array = np.array(img)
            
            # Лёгкая предобработка для повышения контраста/снижения шума
            if len(img_array.shape) == 3:
                gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            else:
                gray = img_array
            
            gray = cv2.convertScaleAbs(gray, alpha=1.5, beta=30)
            denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
            _, thresh = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            kernel = np.ones((1, 1), np.uint8)
            thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
            
            img_processed = Image.fromarray(thresh)
            
            # Перебираем несколько PSM для разных макетов страницы
            text = ""
            for psm_mode in [6, 11, 12]:
                try:
                    text = pytesseract.image_to_string(
                        img_processed,
                        lang='rus+eng',
                        config=f'--psm {psm_mode}'
                    )
                    if len(text.strip()) > 50:
                        break
                except Exception as e:
                    print(f"Ошибка OCR с PSM {psm_mode} для страницы {page_num}: {str(e)}")
                    continue
            
            # Фолбэк: без предобработки
            if not text or len(text.strip()) < 10:
                try:
                    text = pytesseract.image_to_string(
                        img,
                        lang='rus+eng',
                        config='--psm 6'
                    )
                except Exception as e:
                    print(f"Ошибка OCR без предобработки для страницы {page_num}: {str(e)}")
            
            return text if text else ""
        
        except Exception as e:
            print(f"Ошибка OCR для страницы {page_num}: {str(e)}")
            return ""
    
    def _extract_text_with_ocr_full(self, pdf_path: str) -> str:
        """OCR всего PDF, постранично."""
        try:
            images = convert_from_path(pdf_path, dpi=300)
            
            full_text = []
            for page_num, img in enumerate(images, 1):
                print(f"Обрабатываю страницу {page_num} с помощью OCR...")
                
                img_array = np.array(img)
                
                if len(img_array.shape) == 3:
                    gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
                else:
                    gray = img_array
                
                gray = cv2.convertScaleAbs(gray, alpha=1.5, beta=30)
                denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
                _, thresh = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                kernel = np.ones((1, 1), np.uint8)
                thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
                
                img_processed = Image.fromarray(thresh)
                
                text = ""
                for psm_mode in [6, 11, 12]:
                    try:
                        text = pytesseract.image_to_string(
                            img_processed,
                            lang='rus+eng',
                            config=f'--psm {psm_mode}'
                        )
                        if len(text.strip()) > 50:
                            break
                    except Exception as e:
                        continue
                
                if not text or len(text.strip()) < 10:
                    try:
                        text = pytesseract.image_to_string(
                            img,
                            lang='rus+eng',
                            config='--psm 6'
                        )
                    except:
                        pass
                
                if text:
                    full_text.append(f"--- Страница {page_num} ---\n{text}\n")
            
            return "\n".join(full_text)
        
        except Exception as e:
            print(f"Ошибка полного OCR: {str(e)}")
            return ""
    
    def extract_tables(self, pdf_path: str) -> List[List[List[str]]]:
        """Возвращает таблицы со страниц PDF (через pdfplumber)."""
        tables = []
        
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    table_settings = {
                        "vertical_strategy": "lines",
                        "horizontal_strategy": "lines",
                        "intersection_tolerance": 3,
                        "explicit_vertical_lines": [],
                        "explicit_horizontal_lines": [],
                        "snap_tolerance": 3,
                        "join_tolerance": 3,
                        "edge_tolerance": 3,
                        "min_words_vertical": 3,
                        "min_words_horizontal": 1,
                        "intersection_x_tolerance": 3,
                        "intersection_y_tolerance": 3,
                    }
                    
                    page_tables = page.extract_tables(table_settings=table_settings)
                    if page_tables:
                        tables.extend(page_tables)
                        print(f"DEBUG pdf_processor: Найдено таблиц на странице {page_num}: {len(page_tables)}")
        except Exception as e:
            print(f"Ошибка извлечения таблиц: {str(e)}")
        
        return tables
    
    def extract_images(self, pdf_path: str) -> list:
        """Возвращает метаданные изображений, встроенных в PDF (страница, индекс, bbox)."""
        images = []
        
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    page_images = page.images
                    for img_index, img in enumerate(page_images):
                        images.append({
                            "page": page_num,
                            "index": img_index,
                            "bbox": img.get("bbox", [])
                        })
        except Exception as e:
            print(f"Ошибка извлечения изображений: {str(e)}")
        
        return images
    
    def extract_text_from_image(self, image_path: str) -> str:
        """OCR для JPG/PNG изображения, с быстрой предобработкой и перебором PSM."""
        try:
            img = Image.open(image_path)
            img_array = np.array(img)
            
            # Лёгкая предобработка
            if len(img_array.shape) == 3:
                gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            else:
                gray = img_array
            
            gray = cv2.convertScaleAbs(gray, alpha=1.5, beta=30)
            denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
            _, thresh = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            kernel = np.ones((1, 1), np.uint8)
            thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
            
            img_processed = Image.fromarray(thresh)
            
            # Перебор PSM-режимов
            text = ""
            for psm_mode in [6, 11, 12]:
                try:
                    text = pytesseract.image_to_string(
                        img_processed,
                        lang='rus+eng',
                        config=f'--psm {psm_mode}'
                    )
                    if len(text.strip()) > 50:
                        print(f"Успешно использован PSM режим {psm_mode}")
                        break
                except Exception as e:
                    print(f"Ошибка OCR с PSM {psm_mode}: {str(e)}")
                    continue
            
            # Фолбэк: без предобработки
            if not text or len(text.strip()) < 10:
                print("Пробуем OCR без предобработки...")
                try:
                    text = pytesseract.image_to_string(
                        img,
                        lang='rus+eng',
                        config='--psm 6'
                    )
                except Exception as e:
                    print(f"Ошибка OCR без предобработки: {str(e)}")
            
            return text if text else ""
        
        except Exception as e:
            print(f"Ошибка обработки изображения: {str(e)}")
            raise Exception(f"Ошибка обработки изображения: {str(e)}")
    
    def _preprocess_image_for_ocr(self, img: Image.Image) -> Image.Image:
        """Минимальная предобработка изображения для OCR (градации серого, шумоподавление, бинаризация)."""
        try:
            img_array = np.array(img)
            
            if len(img_array.shape) == 3:
                gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            else:
                gray = img_array
            
            gray = cv2.convertScaleAbs(gray, alpha=1.5, beta=30)
            denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
            _, thresh = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            kernel = np.ones((1, 1), np.uint8)
            thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
            
            return Image.fromarray(thresh)
        except Exception as e:
            print(f"Ошибка предобработки изображения: {str(e)}")
            return img
