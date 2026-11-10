# -*- coding: utf-8 -*-
"""Ядро: база данных, справочники, нормативы, расчёты протоколов."""
from __future__ import annotations

import json
import os
import random
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"
DOCS = BASE / "Документы"
PHOTOS = DATA / "photos"
DB_PATH = DATA / "app.db"

for p in (DATA, DOCS, PHOTOS):
    p.mkdir(parents=True, exist_ok=True)

DOC_KINDS = {
    "asphalt": {"label": "Асфальтобетон (ЩМА-16)", "code": "АБ", "short": "Асфальтобетон"},
    "concrete": {"label": "Бетон (кубы)", "code": "Б", "short": "Бетон"},
    "soil": {"label": "Уплотнение грунта / песка", "code": "ГР", "short": "Грунт"},
    "rebar": {"label": "Сварные соединения арматуры", "code": "АР", "short": "Арматура"},
    "asphalt_euro": {"label": "Асфальтобетон (евро, EN 13108-1)", "code": "ЕВ", "short": "Асфальт евро"},
    "concrete_ndt": {"label": "Бетон (неразрушающий контроль)", "code": "НК", "short": "Бетон НК"},
    "soil_proctor": {"label": "Грунт (Proctor: макс. плотность)", "code": "ПР", "short": "Грунт Proctor"},
}

# --------------------------------------------------------------------------
#  Нормативы (справочник). Значения можно менять в разделе «Настройки».
#  Формат: (код, наименование, ед., нижняя граница, верхняя граница, ГОСТ)
#  Границы: None = не нормируется. Для «не менее» — верхняя None.
# --------------------------------------------------------------------------
NORMS: dict = {
    "asphalt": {
        "label": "ЩМА-16, ГОСТ 58406.2-2020 / ГОСТ 9128-2013",
        "intro": "Смесь щебеночно-мастичная асфальтобетонная ЩМА-16",
        "fields": [
            {"key": "water", "name": "Водонасыщение", "unit": "%", "lo": 1.0, "hi": 2.5,
             "gost": "ГОСТ 58406.2-2020, табл. 3"},
            {"key": "por_min", "name": "Пористость минерального остова", "unit": "%", "lo": 15.0, "hi": 19.0,
             "gost": "ГОСТ 58406.2-2020, табл. 3"},
            {"key": "por_res", "name": "Остаточная пористость", "unit": "%", "lo": 2.5, "hi": 4.5,
             "gost": "ГОСТ 58406.2-2020, табл. 3"},
            {"key": "r20", "name": "Предел прочности при сжатии при 20 °C", "unit": "МПа", "lo": 2.5, "hi": None,
             "gost": "ГОСТ 12801-98, п. 14"},
            {"key": "r50", "name": "Предел прочности при сжатии при 50 °C", "unit": "МПа", "lo": 1.2, "hi": None,
             "gost": "ГОСТ 12801-98, п. 14"},
            {"key": "adh", "name": "Сцепление с битумом", "unit": "балл", "lo": 3, "hi": None,
             "gost": "ГОСТ 12801-98, п. 27"},
            {"key": "kup", "name": "Коэффициент уплотнения покрытия", "unit": "-", "lo": 0.98, "hi": None,
             "gost": "СП 78.13330.2012, п. 12"},
        ],
        "conclusion": "Испытанные образцы асфальтобетонной смеси ЩМА-16 по проверенным показателям {res} требованиям ГОСТ 58406.2-2020 и ГОСТ 9128-2013.",
        "meta": [
            {"key": "mix", "name": "Тип смеси", "default": "ЩМА-16"},
            {"key": "mark", "name": "Марка", "default": "I"},
        ],
    },
    "concrete": {
        "label": "Бетон тяжелый, ГОСТ 10180-2012 / ГОСТ 18105-2018",
        "intro": "Образцы-кубы бетона",
        "fields": [],
        "conclusion": "Бетон класса {cls} в возрасте {age} сут. по средней прочности {avg} МПа {res} требованиям ГОСТ 18105-2018.",
        "meta": [
            {"key": "cls", "name": "Класс бетона по проекту", "default": "B25"},
            {"key": "size", "name": "Размер образца, мм", "default": "100"},
            {"key": "age", "name": "Возраст бетона, сут.", "default": "28"},
            {"key": "norm", "name": "Требуемая прочность, МПа", "default": "32.7"},
            {"key": "loads", "name": "Разрушающие нагрузки, кН (через ;)", "default": ""},
        ],
    },
    "soil": {
        "label": "Уплотнение грунта, ГОСТ 22733-2016 / СП 45.13330.2017",
        "intro": "Грунт обратной засыпки / основания",
        "fields": [
            {"key": "kup", "name": "Коэффициент уплотнения", "unit": "-", "lo": 0.95, "hi": None,
             "gost": "СП 45.13330.2017, табл. 6.1"},
            {"key": "w", "name": "Влажность", "unit": "%", "lo": None, "hi": None,
             "gost": "ГОСТ 5180-2015"},
            {"key": "w_opt", "name": "Оптимальная влажность", "unit": "%", "lo": None, "hi": None,
             "gost": "ГОСТ 22733-2016"},
        ],
        "conclusion": "Коэффициент уплотнения грунта {kup} {res} нормативному значению 0,95 (СП 45.13330.2017).",
        "meta": [
            {"key": "soil", "name": "Тип грунта", "default": "Песок средней крупности"},
            {"key": "layer", "name": "Слой / отметка", "default": "0,0–0,3 м"},
        ],
        "extra_inputs": [
            {"key": "rho", "name": "Плотность сухого грунта, г/см³", "default": "1.62"},
            {"key": "rho_max", "name": "Максимальная плотность, г/см³", "default": "1.70"},
            {"key": "w", "name": "Фактическая влажность, %", "default": "9.5"},
            {"key": "w_opt", "name": "Оптимальная влажность, %", "default": "9.0"},
        ],
    },
    "rebar": {
        "label": "Сварные соединения, ГОСТ 10922-2012 / ГОСТ 14098-91",
        "intro": "Соединения стержней арматурного каркаса (срез)",
        "fields": [],
        "conclusion": "Сварные соединения типа {joint} (Ø{d1} + Ø{d2} мм) выдержали испытания на срез; фактические нагрузки {res} нормативные значения.",
        "meta": [
            {"key": "joint", "name": "Тип соединения", "default": "К1-Км"},
            {"key": "d1", "name": "Диаметр рабочего стержня, мм", "default": "10"},
            {"key": "d2", "name": "Диаметр конструктивного стержня, мм", "default": "14"},
            {"key": "norm", "name": "Нормативная нагрузка среза, кН", "default": "58.0"},
            {"key": "loads", "name": "Разрушающие нагрузки, кН (через ;)", "default": ""},
            {"key": "steel", "name": "Класс арматуры", "default": "А500С"},
        ],
    },
    "asphalt_euro": {
        "label": "Асфальтобетон по EN 13108-1 / ГОСТ Р 58406.2",
        "intro": "Смесь асфальтобетонная (европейские показатели)",
        "meta": [],
        "fields": [
            {"key": "pb", "name": "Содержание вяжущего Pb", "unit": "%", "lo": 4.5, "hi": 7.5,
             "gost": "EN 13108-1"},
            {"key": "pa", "name": "Содержание воздушных пустот Pa", "unit": "%", "lo": 2.0, "hi": 5.0,
             "gost": "EN 13108-1"},
            {"key": "vma", "name": "Пустоты в минеральном заполнителе VMA", "unit": "%", "lo": 14.0, "hi": None,
             "gost": "EN 13108-1"},
            {"key": "vfb", "name": "Заполнение пустот битумом VFB", "unit": "%", "lo": 65.0, "hi": 75.0,
             "gost": "EN 13108-1"},
            {"key": "itsr", "name": "Водостойкость ITSR", "unit": "%", "lo": 80.0, "hi": None,
             "gost": "EN 13108-1, прил. B"},
            {"key": "rut", "name": "Глубина колеи при 60 °C", "unit": "мм", "lo": None, "hi": 7.0,
             "gost": "EN 12697-22"},
            {"key": "water", "name": "Коэффициент водостойкости", "unit": "-", "lo": 0.85, "hi": None,
             "gost": "EN 12697-12"},
        ],
        "conclusion": "Асфальтобетонная смесь {res} требованиям EN 13108-1.",
    },
    "concrete_ndt": {
        "label": "Бетон, неразрушающий контроль (ГОСТ 22690-2015)",
        "intro": "Контроль прочности бетона неразрушающим методом",
        "meta": [],
        "fields": [
            {"key": "v1", "name": "Скорость УЗК, обр. 1", "unit": "м/с", "lo": None, "hi": None, "gost": "ГОСТ 22690"},
            {"key": "v2", "name": "Скорость УЗК, обр. 2", "unit": "м/с", "lo": None, "hi": None, "gost": "ГОСТ 22690"},
            {"key": "v3", "name": "Скорость УЗК, обр. 3", "unit": "м/с", "lo": None, "hi": None, "gost": "ГОСТ 22690"},
            {"key": "r1", "name": "Прочность, обр. 1", "unit": "МПа", "lo": 0, "hi": None, "gost": "ГОСТ 22690"},
            {"key": "r2", "name": "Прочность, обр. 2", "unit": "МПа", "lo": 0, "hi": None, "gost": "ГОСТ 22690"},
            {"key": "r3", "name": "Прочность, обр. 3", "unit": "МПа", "lo": 0, "hi": None, "gost": "ГОСТ 22690"},
            {"key": "norm", "name": "Требуемая прочность, МПа", "unit": "МПа", "lo": 0, "hi": None, "gost": "проект"},
        ],
        "conclusion": "Средняя прочность бетона {avg} МПа {res} требуемой {norm} МПа (ГОСТ 22690-2015).",
    },
    "soil_proctor": {
        "label": "Грунт: максимальная плотность (ГОСТ 22733-2016)",
        "intro": "Определение максимальной плотности и оптимальной влажности",
        "meta": [],
        "fields": [
            {"key": "rho_max", "name": "Максимальная плотность, г/см³", "unit": "г/см³", "lo": 1.2, "hi": 2.3,
             "gost": "ГОСТ 22733-2016"},
            {"key": "w_opt", "name": "Оптимальная влажность", "unit": "%", "lo": 5.0, "hi": 25.0,
             "gost": "ГОСТ 22733-2016"},
            {"key": "rho", "name": "Плотность сухого грунта", "unit": "г/см³", "lo": 1.0, "hi": 2.3,
             "gost": "ГОСТ 5180-2015"},
            {"key": "kup", "name": "Коэффициент уплотнения", "unit": "-", "lo": 0.95, "hi": None,
             "gost": "СП 45.13330.2017"},
        ],
        "conclusion": "Максимальная плотность {rho_max} г/см³ при оптимальной влажности {w_opt} %; "
                      "коэффициент уплотнения {kup} {res} норме 0,95.",
    },
}

# --------------------------------------------------------------------------
#  Дополнительные виды испытаний (по формам и примерам протоколов)
# --------------------------------------------------------------------------
DOC_KINDS.update({
    "concrete_core": {"label": "Бетон — керны", "code": "КР", "short": "Керны бетона"},
    "mortar_cube": {"label": "Раствор — кубики", "code": "РР", "short": "Раствор"},
    "protective_layer": {"label": "Защитный слой бетона", "code": "ЗС", "short": "Защитный слой"},
    "waterproofing": {"label": "Гидроизоляция", "code": "ГИ", "short": "Гидроизоляция"},
    "soil_fms_sand": {"label": "ФМС песка", "code": "ФП", "short": "ФМС песок"},
    "soil_fms_soil": {"label": "ФМС грунта", "code": "ФГ", "short": "ФМС грунт"},
    "crushed_stone": {"label": "Щебень", "code": "Щ", "short": "Щебень"},
    "pdu": {"label": "ПДУ — динамический модуль упругости", "code": "ПДУ", "short": "ПДУ"},
    "asphalt_core": {"label": "Асфальт — керны (ГОСТ 9128)", "code": "АК", "short": "Керны асфальта"},
    "asphalt_euro_core": {"label": "Асфальт евро — керны", "code": "ЕК", "short": "Евро керны"},
})

NORMS.update({
    "concrete_core": {
        "label": "Бетон — керны (ГОСТ 28570-2019)",
        "intro": "Прочность бетона по кернам, отобранным из конструкции",
        "meta": [],
        "fields": [
            {"key": "d", "name": "Диаметр керна", "unit": "мм", "lo": 50, "hi": 150, "gost": "ГОСТ 28570-2019"},
            {"key": "h", "name": "Высота керна", "unit": "мм", "lo": 50, "hi": 300, "gost": "ГОСТ 28570-2019"},
            {"key": "area", "name": "Площадь сечения", "unit": "см²", "lo": None, "hi": None, "gost": "—"},
            {"key": "load", "name": "Разрушающая нагрузка", "unit": "кН", "lo": None, "hi": None, "gost": "ГОСТ 28570-2019"},
            {"key": "strength", "name": "Прочность при сжатии", "unit": "МПа", "lo": 10, "hi": None, "gost": "ГОСТ 28570-2019"},
            {"key": "grade", "name": "Проектный класс, МПа", "unit": "МПа", "lo": None, "hi": None, "gost": "проект"},
        ],
        "conclusion": "Прочность бетона по кернам {strength} МПа {res} требованиям проекта.",
    },
    "mortar_cube": {
        "label": "Раствор — кубики (ГОСТ 5802-86)",
        "intro": "Прочность раствора по образцам-кубам 70,7×70,7×70,7 мм",
        "meta": [],
        "fields": [
            {"key": "load1", "name": "Нагрузка, обр. 1", "unit": "кН", "lo": None, "hi": None, "gost": "ГОСТ 5802-86"},
            {"key": "load2", "name": "Нагрузка, обр. 2", "unit": "кН", "lo": None, "hi": None, "gost": "ГОСТ 5802-86"},
            {"key": "load3", "name": "Нагрузка, обр. 3", "unit": "кН", "lo": None, "hi": None, "gost": "ГОСТ 5802-86"},
            {"key": "strength", "name": "Средняя прочность", "unit": "МПа", "lo": 5, "hi": None, "gost": "ГОСТ 5802-86"},
            {"key": "grade", "name": "Проектная марка, МПа", "unit": "МПа", "lo": None, "hi": None, "gost": "проект"},
        ],
        "conclusion": "Прочность раствора {strength} МПа {res} проектной марке.",
    },
    "protective_layer": {
        "label": "Защитный слой бетона (СП 63.13330)",
        "intro": "Толщина защитного слоя бетона",
        "meta": [],
        "fields": [
            {"key": "t1", "name": "Толщина, точка 1", "unit": "мм", "lo": 20, "hi": None, "gost": "СП 63.13330"},
            {"key": "t2", "name": "Толщина, точка 2", "unit": "мм", "lo": 20, "hi": None, "gost": "СП 63.13330"},
            {"key": "t3", "name": "Толщина, точка 3", "unit": "мм", "lo": 20, "hi": None, "gost": "СП 63.13330"},
            {"key": "norm", "name": "Минимально допустимая толщина", "unit": "мм", "lo": None, "hi": None, "gost": "проект"},
        ],
        "conclusion": "Толщина защитного слоя {res} требованиям проекта.",
    },
    "waterproofing": {
        "label": "Гидроизоляция (СП 71.13330)",
        "intro": "Контроль гидроизоляционного покрытия",
        "meta": [],
        "fields": [
            {"key": "thickness", "name": "Толщина покрытия", "unit": "мм", "lo": 2.0, "hi": None, "gost": "СП 71.13330"},
            {"key": "adhesion", "name": "Адгезия к основанию", "unit": "МПа", "lo": 0.5, "hi": None, "gost": "СП 71.13330"},
            {"key": "continuity", "name": "Сплошность (1 — да, 0 — нет)", "unit": "-", "lo": 1, "hi": 1, "gost": "СП 71.13330"},
            {"key": "overlap", "name": "Нахлёст полотен", "unit": "мм", "lo": 100, "hi": None, "gost": "СП 71.13330"},
        ],
        "conclusion": "Гидроизоляционное покрытие {res} требованиям СП 71.13330.",
    },
    "soil_fms_sand": {
        "label": "ФМС песка (ГОСТ 8736, ГОСТ 5180)",
        "intro": "Физико-механические свойства песка",
        "meta": [],
        "fields": [
            {"key": "density", "name": "Плотность", "unit": "г/см³", "lo": 1.4, "hi": 1.9, "gost": "ГОСТ 5180"},
            {"key": "moisture", "name": "Влажность", "unit": "%", "lo": 2, "hi": 15, "gost": "ГОСТ 5180"},
            {"key": "void", "name": "Пустотность", "unit": "%", "lo": None, "hi": 45, "gost": "ГОСТ 8736"},
            {"key": "fines", "name": "Содержание частиц <0,16 мм", "unit": "%", "lo": None, "hi": 10, "gost": "ГОСТ 8736"},
        ],
        "conclusion": "Песок по физико-механическим свойствам {res} требованиям ГОСТ 8736-2014.",
    },
    "soil_fms_soil": {
        "label": "ФМС грунта (ГОСТ 25100, ГОСТ 5180)",
        "intro": "Физико-механические свойства грунта",
        "meta": [],
        "fields": [
            {"key": "density", "name": "Плотность", "unit": "г/см³", "lo": 1.3, "hi": 2.2, "gost": "ГОСТ 5180"},
            {"key": "moisture", "name": "Влажность", "unit": "%", "lo": 3, "hi": 35, "gost": "ГОСТ 5180"},
            {"key": "plastic", "name": "Число пластичности", "unit": "%", "lo": None, "hi": None, "gost": "ГОСТ 5180"},
            {"key": "consistency", "name": "Показатель текучести", "unit": "-", "lo": None, "hi": None, "gost": "ГОСТ 5180"},
        ],
        "conclusion": "Грунт по физико-механическим свойствам {res} проектной документации.",
    },
    "crushed_stone": {
        "label": "Щебень (ГОСТ 8267-93)",
        "intro": "Испытания щебня",
        "meta": [],
        "fields": [
            {"key": "flakiness", "name": "Содержание лещадных зёрен", "unit": "%", "lo": None, "hi": 15, "gost": "ГОСТ 8267-93"},
            {"key": "strength", "name": "Прочность при сжатии", "unit": "МПа", "lo": 60, "hi": None, "gost": "ГОСТ 8267-93"},
            {"key": "frost", "name": "Морозостойкость", "unit": "F", "lo": 50, "hi": None, "gost": "ГОСТ 8267-93"},
            {"key": "water", "name": "Водопоглощение", "unit": "%", "lo": None, "hi": 2.0, "gost": "ГОСТ 8267-93"},
        ],
        "conclusion": "Щебень {res} требованиям ГОСТ 8267-93.",
    },
    "pdu": {
        "label": "ПДУ — динамический модуль упругости (СП 45.13330)",
        "intro": "Контроль уплотнения основания прибором ПДУ",
        "meta": [],
        "fields": [
            {"key": "e1", "name": "Модуль упругости, точка 1", "unit": "МПа", "lo": 50, "hi": None, "gost": "СП 45.13330"},
            {"key": "e2", "name": "Модуль упругости, точка 2", "unit": "МПа", "lo": 50, "hi": None, "gost": "СП 45.13330"},
            {"key": "e3", "name": "Модуль упругости, точка 3", "unit": "МПа", "lo": 50, "hi": None, "gost": "СП 45.13330"},
            {"key": "norm", "name": "Требуемый модуль", "unit": "МПа", "lo": None, "hi": None, "gost": "проект"},
        ],
        "conclusion": "Динамический модуль упругости {res} требованиям проекта.",
    },
    "asphalt_core": {
        "label": "Асфальт — керны (ГОСТ 9128, ГОСТ 12801)",
        "intro": "Испытания кернов асфальтобетонного покрытия",
        "meta": [],
        "fields": [
            {"key": "thickness", "name": "Толщина слоя", "unit": "мм", "lo": 30, "hi": None, "gost": "СП 78.13330"},
            {"key": "density", "name": "Средняя плотность", "unit": "г/см³", "lo": 2.2, "hi": 2.6, "gost": "ГОСТ 12801"},
            {"key": "water", "name": "Водонасыщение", "unit": "%", "lo": 1.0, "hi": 2.5, "gost": "ГОСТ 9128-2013"},
            {"key": "kup", "name": "Коэффициент уплотнения", "unit": "-", "lo": 0.98, "hi": None, "gost": "СП 78.13330"},
        ],
        "conclusion": "Керны асфальтобетона {res} требованиям ГОСТ 9128-2013 и проекта.",
    },
    "asphalt_euro_core": {
        "label": "Асфальт евро — керны (EN 12697)",
        "intro": "Керны асфальтобетона по европейским нормам",
        "meta": [],
        "fields": [
            {"key": "thickness", "name": "Толщина слоя", "unit": "мм", "lo": 30, "hi": None, "gost": "EN 12697-36"},
            {"key": "density", "name": "Объёмная плотность", "unit": "г/см³", "lo": 2.2, "hi": 2.6, "gost": "EN 12697-6"},
            {"key": "voids", "name": "Воздушные пустоты", "unit": "%", "lo": 2.0, "hi": 5.0, "gost": "EN 12697-8"},
        ],
        "conclusion": "Керны асфальтобетона {res} требованиям EN 13108-1.",
    },
})

NORMS_VERSION = 5

COMPANY_VERSION = 2

DEFAULT_COMPANY = {
    "name": "ООО «НИЦ СМК»",
    "full_name": "ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ «НАУЧНО-ИСПЫТАТЕЛЬНЫЙ ЦЕНТР "
                 "СТРОИТЕЛЬНЫХ МАТЕРИАЛОВ И КОНСТРУКЦИЙ»",
    "inn": "9715387698",
    "kpp": "771501001",
    "ogrn": "1207700275903",
    "address": "127081, г. Москва, ул. Вилюйская, д. 11, к. 3",
    "phone": "+7 (916) 006-52-06",
    "email": "ooo.nic-smk@yandex.ru",
    "site": "",
    "accreditation": "№RU.АСК.ИЛ.1132 от 29.12.2022",
    "director": "Земков А.И.",
    "lab_head": "Земков А.И.",
    "executor": "ООО «НИЦ СМК»",
    "logo": "data/branding/logo.png",
    "signature": "data/branding/signature.png",
    "signer1_pos": "Главный специалист",
    "signer1": "Стрючкова К.И.",
    "signer1_img": "data/branding/sign_stryuchkova.png",
    "signer2_pos": "Руководитель лаборатории",
    "signer2": "Бунин Н.И.",
    "signer2_img": "data/branding/sign_bunin.png",
    "code_asphalt": "11", "code_concrete": "25", "code_soil": "14", "code_rebar": "",
    "code_asphalt_euro": "12", "code_concrete_ndt": "25", "code_soil_proctor": "14",
    "stamp": "data/branding/stamp.png",
    "signature_note": "Протокол оформлен по результатам испытаний, проведённых в лаборатории.",
}

DEFAULT_EMPLOYEES = [
    {"name": "Земков А.И.", "position": "Начальник испытательной лаборатории"},
    {"name": "Стрючкова К.И.", "position": "Главный специалист"},
    {"name": "Лупанова", "position": "Инженер-лаборант"},
    {"name": "Барамыгина", "position": "Инженер"},
    {"name": "Мартынов", "position": "Инженер"},
]

OBJECTS_SEED = [
    "БОГОРОДСКИЙ Г.О", "БРОННИЦЫ", "ВОСКРЕСЕНСК", "ГБОУ ДПО МЦВП", "ГКУ УДМС",
    "ДЗЕРЖИНСК", "ДУБНА", "ЗАРАЙСК", "КОЛОМНА", "ЛУХОВИЦЫ", "ЛЮБЕРЦЫ", "МВК ТРЕСТ",
    "МОСКВА", "НОРАЭР", "ОЗЕРЫ", "ПАВЛОВСКИЙ ПОСАД", "ПОДОЛЬСК", "ПУЩИНО",
    "ТАЛДОМ", "ШАТУРА", "ШАХОВСКАЯ", "ЭЛЕКТРОСТАЛЬ",
]


# --------------------------------------------------------------------------
#  База данных
# --------------------------------------------------------------------------
def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


def init_db() -> None:
    con = connect()
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS objects (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
            address TEXT DEFAULT '', customer TEXT DEFAULT '', note TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS contracts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, number TEXT, cdate TEXT, end_date TEXT,
            subject TEXT, price REAL, customer TEXT, status TEXT, note TEXT);
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, position TEXT, signature TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS protocols (
            id INTEGER PRIMARY KEY AUTOINCREMENT, number TEXT, pdate TEXT, kind TEXT,
            object_name TEXT, customer TEXT, sample TEXT, payload TEXT,
            draft INTEGER DEFAULT 0, created_at TEXT, file TEXT);
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT, number TEXT, rdate TEXT, date_from TEXT,
            date_to TEXT, object_name TEXT, customer TEXT, contract TEXT, payload TEXT,
            created_at TEXT, file TEXT);
        CREATE TABLE IF NOT EXISTS counters (kind TEXT, year INTEGER, value INTEGER, PRIMARY KEY (kind, year));
        CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT, object_id INTEGER, object_name TEXT,
            edate TEXT, author TEXT, comment TEXT, photos TEXT, tags TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS object_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT, object_id INTEGER, rel TEXT, name TEXT,
            kind TEXT, size INTEGER, added_at TEXT, UNIQUE(object_id, rel));
        CREATE TABLE IF NOT EXISTS protocol_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, protocol_id INTEGER, version INTEGER,
            file TEXT, payload TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS report_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, report_id INTEGER, version INTEGER,
            file TEXT, payload TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS kp (
            id INTEGER PRIMARY KEY AUTOINCREMENT, number TEXT UNIQUE, kdate TEXT,
            customer TEXT, object TEXT, total REAL DEFAULT 0, file TEXT, items TEXT);
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, user_id INTEGER, user_name TEXT,
            role TEXT, action TEXT, entity TEXT, entity_id INTEGER, details TEXT);
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, login TEXT UNIQUE,
            pin TEXT, role TEXT, active INTEGER DEFAULT 1, created_at TEXT);
        CREATE TABLE IF NOT EXISTS user_extra (
            user_id INTEGER PRIMARY KEY, phone TEXT, status TEXT DEFAULT 'active',
            tg_chat TEXT, otp TEXT, otp_exp TEXT, link_token TEXT);
        CREATE TABLE IF NOT EXISTS object_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE);
        CREATE TABLE IF NOT EXISTS object_docs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, object_id INTEGER, path TEXT, title TEXT,
            kind TEXT, added_at TEXT, UNIQUE(object_id, path));
        CREATE TABLE IF NOT EXISTS numbering (
            kind TEXT PRIMARY KEY, next_value INTEGER NOT NULL, updated_at TEXT);
        CREATE TABLE IF NOT EXISTS number_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, value INTEGER,
            doc_type TEXT, doc_id INTEGER, object_name TEXT, created_at TEXT);
        """
    )
    # миграция объектов и записей
    rcols = {r["name"] for r in con.execute("PRAGMA table_info(reports)")}
    if "kind" not in rcols:
        con.execute("ALTER TABLE reports ADD COLUMN kind TEXT DEFAULT 'weekly'")

    ocols = {r["name"] for r in con.execute("PRAGMA table_info(objects)")}
    for col, ddl in (("folder", "TEXT DEFAULT ''"), ("status", "TEXT DEFAULT 'active'"),
                     ("contract", "TEXT DEFAULT ''"), ("archived_at", "TEXT DEFAULT ''"),
                     ("code", "TEXT DEFAULT ''"), ("report_freq", "TEXT DEFAULT ''"),
                     ("report_start", "TEXT DEFAULT ''"), ("report_next", "TEXT DEFAULT ''"),
                     ("report_auto", "INTEGER DEFAULT 1"), ("report_day", "INTEGER DEFAULT 1"),
                     ("contractor", "TEXT DEFAULT ''"), ("object_title", "TEXT DEFAULT ''"),
                     ("city", "TEXT DEFAULT ''"), ("customer_email", "TEXT DEFAULT ''"), ("customer_inn", "TEXT DEFAULT ''"),
                     ("customer_phone", "TEXT DEFAULT ''"), ("obj_type", "TEXT DEFAULT 'contract'"),
                     ("contract_id", "INTEGER DEFAULT 0"), ("group_id", "INTEGER DEFAULT 0")):
        if col not in ocols:
            con.execute(f"ALTER TABLE objects ADD COLUMN {col} {ddl}")
    con.execute("CREATE TABLE IF NOT EXISTS object_groups (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE)")
    ecols = {r["name"] for r in con.execute("PRAGMA table_info(entries)")}
    if "files" not in ecols:
        con.execute("ALTER TABLE entries ADD COLUMN files TEXT DEFAULT '[]'")

    # миграция колонок протокола
    cols = {r["name"] for r in con.execute("PRAGMA table_info(protocols)")}
    for col in ("lab_no", "act_no"):
        if col not in cols:
            con.execute(f"ALTER TABLE protocols ADD COLUMN {col} TEXT DEFAULT ''")

    # сиды
    if not con.execute("SELECT 1 FROM settings WHERE key='company'").fetchone():
        con.execute("INSERT INTO settings(key,value) VALUES (?,?)", ("company", json.dumps(DEFAULT_COMPANY, ensure_ascii=False)))
    ver_row = con.execute("SELECT value FROM settings WHERE key='company_version'").fetchone()
    if not ver_row or json.loads(ver_row["value"]) != COMPANY_VERSION:
        con.execute("INSERT INTO settings(key,value) VALUES ('company',?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (json.dumps(DEFAULT_COMPANY, ensure_ascii=False),))
        con.execute("INSERT INTO settings(key,value) VALUES ('company_version',?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (json.dumps(COMPANY_VERSION),))
    if not con.execute("SELECT 1 FROM settings WHERE key='norms'").fetchone():
        con.execute("INSERT INTO settings(key,value) VALUES (?,?)", ("norms", json.dumps(NORMS, ensure_ascii=False)))
        con.execute("INSERT INTO settings(key,value) VALUES (?,?)", ("norms_version", json.dumps(NORMS_VERSION)))
    if not con.execute("SELECT 1 FROM employees").fetchone():
        for e in DEFAULT_EMPLOYEES:
            con.execute("INSERT INTO employees(name,position) VALUES (?,?)", (e["name"], e["position"]))
    if not con.execute("SELECT 1 FROM objects").fetchone():
        for name in OBJECTS_SEED:
            con.execute("INSERT OR IGNORE INTO objects(name) VALUES (?)", (name,))
    if not con.execute("SELECT 1 FROM numbering LIMIT 1").fetchone():
        found = {}
        try:
            found = registry_max()
        except Exception:
            found = {}
        now = datetime.now().isoformat(timespec="seconds")
        for kind in NUMBER_KINDS:
            start = (found.get(kind) or 0) + 1
            con.execute("INSERT OR REPLACE INTO numbering(kind,next_value,updated_at) VALUES (?,?,?)",
                        (kind, max(1, start), now))
        if found:
            con.execute("INSERT INTO settings(key,value) VALUES ('numbering_synced_at',?) "
                        "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (json.dumps(now),))
    con.commit()
    con.close()
    sync_norms()


def get_setting(key: str, default=None):
    con = connect()
    row = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    con.close()
    if not row:
        return default
    try:
        return json.loads(row["value"])
    except Exception:
        return row["value"]


def set_setting(key: str, value) -> None:
    con = connect()
    con.execute("INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(value, ensure_ascii=False)))
    con.commit()
    con.close()


def norms() -> dict:
    data = get_setting("norms", NORMS) or NORMS
    return {k: v for k, v in data.items() if not k.startswith("__")}


def sync_norms() -> None:
    """Обновляет структуру справочника, сохраняя введённые пользователем границы."""
    if get_setting("norms_version") == NORMS_VERSION:
        return
    stored = get_setting("norms", {}) or {}
    fresh = json.loads(json.dumps(NORMS, ensure_ascii=False))
    for kind, n in fresh.items():
        old = stored.get(kind) or {}
        old_fields = {f.get("key"): f for f in old.get("fields", []) if isinstance(f, dict)}
        for f in n.get("fields", []):
            of = old_fields.get(f.get("key"))
            if of:
                f["lo"] = of.get("lo", f.get("lo"))
                f["hi"] = of.get("hi", f.get("hi"))
                if of.get("name"):
                    f["name"] = of["name"]
    set_setting("norms", fresh)
    set_setting("norms_version", NORMS_VERSION)


def company() -> dict:
    c = dict(DEFAULT_COMPANY)
    c.update(get_setting("company", {}) or {})
    return c


def next_number(kind: str, year: int | None = None, peek: bool = False) -> str:
    year = year or date.today().year
    con = connect()
    row = con.execute("SELECT value FROM counters WHERE kind=? AND year=?", (kind, year)).fetchone()
    cur = row["value"] if row else 0
    if not peek:
        con.execute("INSERT INTO counters(kind,year,value) VALUES (?,?,?) ON CONFLICT(kind,year) DO UPDATE SET value=excluded.value",
                    (kind, year, cur + 1))
        con.commit()
    con.close()
    code = DOC_KINDS.get(kind, {}).get("code", "П")
    return f"{cur + 1:02d}-{code}/{str(year)[2:]}"


def set_object_folder(object_id: int, folder: str) -> None:
    con = connect()
    con.execute("UPDATE objects SET folder=? WHERE id=?", (folder, object_id))
    con.commit()
    con.close()


def find_object_folder(object_name: str) -> str:
    """Ищет папку объекта в рабочих каталогах Яндекс.Диска."""
    import os
    import re as _re
    roots = [BASE.parent / "РАБОЧАЯ" / "ОБЪЕКТЫ", BASE.parent / "РАБОЧАЯ" / "СТРОИТЕЛЬНЫЙ КОНТРОЛЬ",
             BASE.parent / "РАБОЧАЯ" / "ОБСЛЕДОВАНИЕ"]
    tokens = [w.lower() for w in _re.split(r"[^\wа-яА-ЯёЁ]+", object_name) if len(w) > 2]
    if not tokens:
        return ""
    best, best_score = "", 0
    for base in roots:
        if not base.exists():
            continue
        for cur, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if not d.startswith((".", "~", "_"))]
            low = cur.lower()
            score = sum(1 for tok in tokens if tok in low)
            if score > best_score:
                best, best_score = cur, score
            if score == len(tokens):
                return cur
    return best if best_score >= max(1, len(tokens) - 1) else ""


def add_months(d, months: int):
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    day = min(d.day, [31, 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28,
                      31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1])
    return date(y, m, day)


def next_report_date(base, freq: str):
    b = base if isinstance(base, date) else datetime.strptime(str(base)[:10], "%Y-%m-%d").date()
    if freq == "weekly":
        return b + timedelta(days=7)
    if freq == "monthly":
        return add_months(b, 1)
    return b


def set_object_schedule(object_id: int, freq: str, start: str = "", day: int = 1,
                        auto: bool = True) -> dict:
    """Задаёт периодичность отчётности и ближайшую дату."""
    today = date.today()
    try:
        start_d = datetime.strptime((start or today.isoformat())[:10], "%Y-%m-%d").date()
    except ValueError:
        start_d = today
    nxt = start_d
    guard = 0
    while nxt <= today and guard < 400:
        nxt = next_report_date(nxt, freq)
        guard += 1
    con = connect()
    con.execute("UPDATE objects SET report_freq=?, report_start=?, report_next=?, report_day=?, report_auto=? "
                "WHERE id=?", (freq, start_d.isoformat(), nxt.isoformat(), int(day or 1),
                               1 if auto else 0, object_id))
    con.commit()
    row = con.execute("SELECT report_freq,report_start,report_next,report_day,report_auto "
                      "FROM objects WHERE id=?", (object_id,)).fetchone()
    con.close()
    return dict(row) if row else {}


def due_objects(today_iso: str | None = None) -> list[dict]:
    today_iso = today_iso or date.today().isoformat()
    con = connect()
    rows = [dict(r) for r in con.execute(
        "SELECT * FROM objects WHERE report_freq IN ('weekly','monthly') AND report_auto=1 "
        "AND report_next<>'' AND report_next<=? AND status='active' ORDER BY report_next", (today_iso,))]
    con.close()
    return rows


def set_object_status(object_id: int, status: str) -> None:
    con = connect()
    if status == "archive":
        con.execute("UPDATE objects SET status='archive', archived_at=? WHERE id=?",
                    (date.today().isoformat(), object_id))
    else:
        con.execute("UPDATE objects SET status='active', archived_at='' WHERE id=?", (object_id,))
    con.commit()
    con.close()


def copy_docs_to_object(object_id: int) -> list[str]:
    """Копирует сформированные протоколы и отчёты в папку объекта на Яндекс.Диске."""
    import shutil
    con = connect()
    obj = con.execute("SELECT * FROM objects WHERE id=?", (object_id,)).fetchone()
    if not obj or not obj["folder"]:
        con.close()
        return []
    folder = Path(obj["folder"]) / "_СМК документы"
    folder.mkdir(parents=True, exist_ok=True)
    reports_dir = Path(obj["folder"]) / "ОТЧЕТЫ"
    try:
        reports_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        reports_dir = folder
    name = obj["name"]
    files = [r["file"] for r in con.execute(
        "SELECT file FROM protocols WHERE object_name LIKE ?", (f"%{name[:40]}%",))]
    report_files = [r["file"] for r in con.execute(
        "SELECT file FROM reports WHERE object_name LIKE ?", (f"%{name[:40]}%",))]
    con.close()
    copied = []
    for rel in files:
        if not rel:
            continue
        src = BASE / rel
        if src.exists():
            dst = folder / src.name
            if not dst.exists():
                shutil.copy2(src, dst)
            copied.append(str(dst))
    for rel in report_files:
        if not rel:
            continue
        for ext in (".docx", ".pdf"):
            src = (BASE / rel).with_suffix(ext)
            if src.exists():
                dst = reports_dir / src.name
                if not dst.exists():
                    shutil.copy2(src, dst)
                copied.append(str(dst))
    return copied


def list_table(table: str) -> list[dict]:
    con = connect()
    rows = [dict(r) for r in con.execute(f"SELECT * FROM {table}")]
    con.close()
    return rows


def ensure_group(name: str) -> int:
    name = (name or "").strip()
    if not name:
        return 0
    con = connect()
    row = con.execute("SELECT id FROM object_groups WHERE name=?", (name,)).fetchone()
    if row:
        con.close()
        return row["id"]
    cur = con.execute("INSERT INTO object_groups(name) VALUES (?)", (name,))
    con.commit()
    gid = cur.lastrowid
    con.close()
    return gid


def add_object(name: str, address: str = "", customer: str = "", obj_type: str = "contract",
               contract_id: int = 0) -> int:
    con = connect()
    cur = con.execute(
        "INSERT OR IGNORE INTO objects(name,address,customer,obj_type,contract_id) VALUES (?,?,?,?,?)",
        (name, address, customer, obj_type or "contract", int(contract_id or 0)))
    con.commit()
    oid = cur.lastrowid
    if not oid:
        oid = con.execute("SELECT id FROM objects WHERE name=?", (name,)).fetchone()["id"]
    con.close()
    return oid


def add_contract(data: dict) -> int:
    con = connect()
    cur = con.execute(
        "INSERT INTO contracts(number,cdate,end_date,subject,price,customer,status,note) VALUES (?,?,?,?,?,?,?,?)",
        (data.get("number", ""), data.get("cdate", ""), data.get("end_date", ""), data.get("subject", ""),
         data.get("price") or 0, data.get("customer", ""), data.get("status", "Актуальные"), data.get("note", "")),
    )
    con.commit()
    cid = cur.lastrowid
    con.close()
    return cid


def import_contracts_from_excel(path: str | None = None) -> int:
    """Импорт контрактов из файла «Контракты ПИК 2026.xlsx» (лист «Актуальные»)."""
    import openpyxl
    candidates = [Path(path)] if path else [
        BASE.parent / "Контракты ПИК 2026.xlsx",
        BASE.parent / "Исполнение контрактов.xlsx",
    ]
    src = next((p for p in candidates if p and p.exists()), None)
    if not src:
        return 0
    wb = openpyxl.load_workbook(src, data_only=True)
    ws = wb["Актуальные"] if "Актуальные" in wb.sheetnames else wb.worksheets[0]
    added = 0
    con = connect()
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or not row[0]:
            continue
        num = str(row[1] or "").split("\n")[0].strip()
        if not num:
            continue
        if con.execute("SELECT 1 FROM contracts WHERE number=?", (num,)).fetchone():
            continue
        def s(v):
            if isinstance(v, datetime):
                return v.strftime("%d.%m.%Y")
            return str(v or "").strip()
        con.execute(
            "INSERT INTO contracts(number,cdate,end_date,subject,price,customer,status,note) VALUES (?,?,?,?,?,?,?,?)",
            (num, s(row[2]), s(row[3]), s(row[4]), row[5] or 0, s(row[6]), "Актуальные", s(row[8]) if len(row) > 8 else ""),
        )
        added += 1
    con.commit()
    con.close()
    return added


# --------------------------------------------------------------------------
#  Расчёты
# --------------------------------------------------------------------------
def fmt_num(v, decimals: int = 2) -> str:
    if v is None or v == "":
        return "—"
    try:
        f = float(str(v).replace(",", "."))
    except Exception:
        return str(v)
    s = f"{f:.{decimals}f}".rstrip("0").rstrip(".")
    return s.replace(".", ",") if s else "0"


def check_value(v: float, lo, hi) -> bool:
    if v is None:
        return True
    if lo is not None and v < lo - 1e-9:
        return False
    if hi is not None and v > hi + 1e-9:
        return False
    return True


def norm_text(lo, hi, unit: str) -> str:
    if lo is not None and hi is not None:
        return f"{fmt_num(lo)}–{fmt_num(hi)} {unit}".strip()
    if lo is not None:
        return f"не менее {fmt_num(lo)} {unit}".strip()
    if hi is not None:
        return f"не более {fmt_num(hi)} {unit}".strip()
    return "—"


def gen_value(lo, hi, decimals: int = 2) -> float:
    if lo is not None and hi is not None:
        span = hi - lo
        v = random.uniform(lo + span * 0.15, hi - span * 0.15)
    elif lo is not None:
        v = lo * random.uniform(1.05, 1.22) if lo else random.uniform(0.5, 1.5)
    elif hi is not None:
        v = hi * random.uniform(0.78, 0.95)
    else:
        v = random.uniform(1, 10)
    return round(v, decimals)


def _loads(meta: dict) -> list[float]:
    raw = str(meta.get("loads", "") or "").replace(",", ".")
    parts = [p for p in raw.replace(";", " ").split() if p]
    out = []
    for p in parts:
        try:
            out.append(float(p))
        except ValueError:
            pass
    return out


def calculate(kind: str, meta: dict) -> dict:
    """Возвращает строки таблицы результатов, заключение и служебные данные."""
    n = norms().get(kind, NORMS.get(kind, {}))
    meta = dict(meta or {})
    rows: list[dict] = []
    ok_all = True
    conclusion = ""
    extra: dict = {}

    complete = True
    if kind == "asphalt":
        for f in n["fields"]:
            raw = meta.get(f["key"], "")
            v = None
            if raw not in (None, ""):
                try:
                    v = float(str(raw).replace(",", "."))
                except ValueError:
                    v = None
            missing = v is None
            complete = complete and not missing
            ok = check_value(v, f["lo"], f["hi"]) if not missing else True
            ok_all = ok_all and ok
            rows.append({"key": f["key"], "name": f["name"], "unit": f["unit"],
                         "req": norm_text(f["lo"], f["hi"], f["unit"]), "gost": f["gost"],
                         "value": fmt_num(v, 2 if f["unit"] != "балл" else 0) if not missing else "—",
                         "ok": ok, "missing": missing})
        if complete:
            res = "соответствуют" if ok_all else "не соответствуют"
            conclusion = n["conclusion"].format(res=res)
        else:
            conclusion = "Заполните результаты измерений: часть показателей не указана."

    elif kind == "concrete":
        size = float(meta.get("size", 150) or 150)
        loads = _loads(meta)
        if not loads:
            complete = False
            conclusion = "Укажите разрушающие нагрузки по образцам (кН)."
        else:
            area_mm2 = size * size
            k_scale = {100: 0.95, 150: 1.0, 200: 1.05}.get(int(size), 1.0)
            strengths = [round(f * 1000 / area_mm2 * k_scale, 2) for f in loads]  # кН*1000/мм² = МПа
            avg = round(sum(strengths) / len(strengths), 2)
            disp = sum((s - avg) ** 2 for s in strengths) / max(len(strengths) - 1, 1)
            cv = round((disp ** 0.5) / avg * 100, 1) if avg else 0
            for i, (f, r) in enumerate(zip(loads, strengths), 1):
                rows.append({"key": f"s{i}", "name": f"Образец №{i}: разрушающая нагрузка", "unit": "кН",
                             "req": "—", "gost": "ГОСТ 10180-2012", "value": fmt_num(f, 1), "ok": True})
                rows.append({"key": f"r{i}", "name": f"Образец №{i}: прочность при сжатии", "unit": "МПа",
                             "req": "—", "gost": "ГОСТ 10180-2012", "value": fmt_num(r, 2), "ok": True})
            need = float(str(meta.get("norm", "32.7")).replace(",", ".") or 0)
            ok_all = avg >= need * 0.95
            rows += [
                {"key": "avg", "name": "Средняя прочность", "unit": "МПа", "req": f"не менее {fmt_num(need)}",
                 "gost": "ГОСТ 18105-2018", "value": fmt_num(avg, 2), "ok": ok_all},
                {"key": "cv", "name": "Коэффициент вариации", "unit": "%", "req": "не более 13,5",
                 "gost": "ГОСТ 18105-2018", "value": fmt_num(cv, 1), "ok": cv <= 13.5},
            ]
            ok_all = ok_all and cv <= 13.5
            extra = {"avg": fmt_num(avg, 2), "cv": fmt_num(cv, 1), "class": meta.get("cls", "")}
            conclusion = n["conclusion"].format(cls=meta.get("cls", ""), age=meta.get("age", "28"),
                                                avg=fmt_num(avg, 2),
                                                res="соответствует" if ok_all else "не соответствует")

    elif kind in ("asphalt_euro", "concrete_ndt", "soil_proctor"):
        vals = {}
        for f in n["fields"]:
            raw = meta.get(f["key"], "")
            try:
                v = float(str(raw).replace(",", ".")) if str(raw).strip() else None
            except ValueError:
                v = None
            vals[f["key"]] = v
            missing = v is None and f["key"] != "norm"
            complete = complete and not missing
            ok = check_value(v, f["lo"], f["hi"]) if v is not None else True
            ok_all = ok_all and ok
            rows.append({"key": f["key"], "name": f["name"], "unit": f["unit"],
                         "req": norm_text(f["lo"], f["hi"], f["unit"]), "gost": f["gost"],
                         "value": fmt_num(v, 2) if v is not None else "—", "ok": ok,
                         "missing": v is None})
        ctx = dict(vals)
        ctx["res"] = "соответствует" if ok_all else "не соответствует"
        if kind == "concrete_ndt":
            rs = [v for k, v in vals.items() if k.startswith("r") and v]
            ctx["avg"] = fmt_num(sum(rs) / len(rs), 1) if rs else "—"
            ctx["norm"] = fmt_num(meta.get("norm"), 1)
            ctx["res"] = "соответствует" if all((x or 0) >= float(meta.get("norm") or 0) for x in rs) else "не соответствует"
        if kind == "soil_proctor":
            ctx["res"] = "соответствует" if (vals.get("kup") or 0) >= 0.95 else "не соответствует"
        conclusion = n["conclusion"].format(**{k: (fmt_num(v, 3) if isinstance(v, float) else v)
                                               for k, v in ctx.items()})
        complete = complete and all(v is not None for k, v in vals.items() if k != "norm")

    elif kind == "soil":
        try:
            rho = float(str(meta.get("rho", "1.62")).replace(",", "."))
            rho_max = float(str(meta.get("rho_max", "1.70")).replace(",", "."))
        except ValueError:
            rho, rho_max = 1.62, 1.70
        kup = round(rho / rho_max, 3) if rho_max else 0
        ok_all = kup >= 0.95
        rows = [
            {"key": "rho", "name": "Плотность сухого грунта", "unit": "г/см³", "req": "—",
             "gost": "ГОСТ 5180-2015", "value": fmt_num(rho, 2), "ok": True},
            {"key": "rho_max", "name": "Максимальная плотность (прибор СоюздорНИИ)", "unit": "г/см³", "req": "—",
             "gost": "ГОСТ 22733-2016", "value": fmt_num(rho_max, 2), "ok": True},
            {"key": "kup", "name": "Коэффициент уплотнения", "unit": "-", "req": "не менее 0,95",
             "gost": "СП 45.13330.2017", "value": fmt_num(kup, 3), "ok": ok_all},
            {"key": "w", "name": "Влажность", "unit": "%", "req": "—", "gost": "ГОСТ 5180-2015",
             "value": fmt_num(meta.get("w"), 1), "ok": True},
        ]
        conclusion = n["conclusion"].format(kup=fmt_num(kup, 3), res="соответствует" if ok_all else "не соответствует")
        extra = {"kup": fmt_num(kup, 3)}

    elif kind == "rebar":
        loads = _loads(meta)
        norm_load = float(str(meta.get("norm", "58.0")).replace(",", ".") or 58)
        for i, f in enumerate(loads, 1):
            ok = f >= norm_load
            ok_all = ok_all and ok
            rows.append({"key": f"p{i}", "name": f"Образец №{i}: разрушающая нагрузка", "unit": "кН",
                         "req": f"не менее {fmt_num(norm_load, 1)}", "gost": "ГОСТ 10922-2012",
                         "value": fmt_num(f, 1), "ok": ok})
        if loads:
            avg = sum(loads) / len(loads)
            rows.append({"key": "avg", "name": "Средняя разрушающая нагрузка", "unit": "кН", "req": "—",
                         "gost": "ГОСТ 10922-2012", "value": fmt_num(avg, 1), "ok": True})
            conclusion = n["conclusion"].format(joint=meta.get("joint", "К1-Км"), d1=meta.get("d1", "10"),
                                                d2=meta.get("d2", "14"),
                                                res="превышают" if ok_all else "ниже")
            extra = {"avg": fmt_num(avg, 1)}
        else:
            complete = False
            conclusion = "Укажите разрушающие нагрузки по образцам (кН)."

    return {"rows": rows, "ok": ok_all, "complete": complete,
            "conclusion": conclusion, "extra": extra}


def fill_demo(kind: str, meta: dict) -> dict:
    """Заполняет входные данные правдоподобными значениями (демо/черновик)."""
    meta = dict(meta or {})
    n = norms().get(kind, NORMS.get(kind, {}))
    for f in n.get("meta", []):
        if meta.get(f["key"]) in (None, ""):
            meta[f["key"]] = f.get("default", "")
    if kind == "asphalt":
        for f in n["fields"]:
            meta[f["key"]] = fmt_num(gen_value(f["lo"], f["hi"], 2 if f["unit"] != "балл" else 0),
                                     2 if f["unit"] != "балл" else 0)
    elif kind == "concrete":
        need = float(str(meta.get("norm", "32.7")).replace(",", ".") or 32.7)
        size = float(meta.get("size", 150) or 150)
        k_scale = {100: 0.95, 150: 1.0, 200: 1.05}.get(int(size), 1.0)
        base_load = need * (size * size) / 1000 / k_scale
        loads = [round(base_load * random.uniform(1.04, 1.14), 1) for _ in range(3)]
        meta["loads"] = "; ".join(str(x) for x in loads)
    elif kind == "soil":
        rho_max = 1.70
        meta["rho_max"] = fmt_num(rho_max, 2)
        meta["rho"] = fmt_num(rho_max * random.uniform(0.955, 0.985), 3)
        meta["w"] = fmt_num(random.uniform(8.0, 11.5), 1)
        meta["w_opt"] = fmt_num(random.uniform(8.5, 10.5), 1)
    elif kind == "rebar":
        base = float(str(meta.get("norm", "58.0")).replace(",", ".") or 58)
        meta["loads"] = "; ".join(str(round(base * random.uniform(1.03, 1.12), 1)) for _ in range(3))
    return meta


# --------------------------------------------------------------------------
#  Полевые записи и документы объектов
# --------------------------------------------------------------------------
DOC_EXT = {".docx", ".doc", ".pdf", ".xlsx", ".xls", ".jpg", ".jpeg", ".png", ".dwg", ".dxf", ".txt", ".md"}


def add_entry(object_id: int, object_name: str, edate: str, author: str,
              comment: str, photos: list, tags: str = "", files: list | None = None,
              activity: str = "") -> int:
    con = connect()
    cols = {r["name"] for r in con.execute("PRAGMA table_info(entries)")}
    if "activity" not in cols:
        con.execute("ALTER TABLE entries ADD COLUMN activity TEXT DEFAULT ''")
    cur = con.execute(
        "INSERT INTO entries(object_id,object_name,edate,author,comment,photos,tags,created_at,files,activity)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (object_id or 0, object_name, edate, author, comment,
         json.dumps(photos or [], ensure_ascii=False), tags, date.today().isoformat(),
         json.dumps(files or [], ensure_ascii=False), activity))
    con.commit()
    eid = cur.lastrowid
    con.close()
    return eid


def entries(object_id: int | None = None, limit: int = 300) -> list[dict]:
    con = connect()
    if object_id:
        rows = con.execute("SELECT * FROM entries WHERE object_id=? ORDER BY edate DESC, id DESC LIMIT ?",
                           (object_id, limit)).fetchall()
    else:
        rows = con.execute("SELECT * FROM entries ORDER BY edate DESC, id DESC LIMIT ?", (limit,)).fetchall()
    con.close()
    out = []
    for r in rows:
        d = dict(r)
        for key in ("photos", "files"):
            try:
                d[key] = json.loads(d.get(key) or "[]")
            except Exception:
                d[key] = []
        out.append(d)
    return out


def delete_entry(eid: int) -> None:
    con = connect()
    row = con.execute("SELECT photos FROM entries WHERE id=?", (eid,)).fetchone()
    con.execute("DELETE FROM entries WHERE id=?", (eid,))
    con.commit()
    con.close()
    if row:
        try:
            for p in json.loads(row["photos"] or "[]"):
                q = Path(p.get("path") if isinstance(p, dict) else p)
                if q.exists() and str(q).startswith(str(PHOTOS)):
                    q.unlink()
        except Exception:
            pass


def object_docs(object_id: int) -> list[dict]:
    con = connect()
    rows = [dict(r) for r in con.execute(
        "SELECT * FROM object_docs WHERE object_id=? ORDER BY id DESC", (object_id,))]
    con.close()
    for r in rows:
        r["exists"] = Path(r["path"]).exists()
        r["size"] = Path(r["path"]).stat().st_size if r["exists"] else 0
    return rows


def add_object_doc(object_id: int, path: str, title: str = "") -> None:
    q = Path(path)
    con = connect()
    con.execute("INSERT OR IGNORE INTO object_docs(object_id,path,title,kind,added_at) VALUES (?,?,?,?,?)",
                (object_id, str(q), title or q.name, q.suffix.lower().lstrip("."), date.today().isoformat()))
    con.commit()
    con.close()


def scan_object_docs(object_id: int, object_name: str, limit: int = 400) -> int:
    """Ищет документы проекта в рабочих папках Яндекс.Диска по названию объекта.

    Обходит дерево, но заходит только в папки, в пути которых встречается слово из
    названия объекта — это в разы быстрее полного обхода облачной папки.
    """
    import os
    import re as _re
    root = BASE.parent
    roots = [root / "РАБОЧАЯ" / "ОБЪЕКТЫ", root / "РАБОЧАЯ" / "СТРОИТЕЛЬНЫЙ КОНТРОЛЬ",
             root / "РАБОЧАЯ" / "ОБСЛЕДОВАНИЕ", root / "РАБОЧАЯ" / "СУДЕБНЫЕ ДЕЛА"]
    tokens = [w.lower() for w in _re.split(r"[^\wа-яА-ЯёЁ]+", object_name) if len(w) > 2]
    if not tokens:
        return 0
    added = 0
    for base in roots:
        if not base.exists():
            continue
        visited = 0
        for cur, dirs, files in os.walk(base):
            visited += 1
            if visited > 8000:
                break
            dirs[:] = [d for d in dirs if not d.startswith((".", "~", "_"))]
            low = cur.lower()
            hits = sum(1 for tok in tokens if tok in low)
            if hits == 0:
                continue
            for fn in files:
                if fn.startswith((".", "~$")):
                    continue
                if Path(fn).suffix.lower() not in DOC_EXT:
                    continue
                add_object_doc(object_id, str(Path(cur) / fn))
                added += 1
                if added >= limit:
                    break
            if added >= limit:
                break
        if added >= limit:
            break
    con = connect()
    n = con.execute("SELECT COUNT(*) c FROM object_docs WHERE object_id=?", (object_id,)).fetchone()["c"]
    con.close()
    return n


def doc_text(path: str, limit_chars: int = 4000) -> str:
    """Быстрое извлечение текста из docx/xlsx/txt для контекста ИИ."""
    q = Path(path)
    if not q.exists():
        return ""
    ext = q.suffix.lower()
    try:
        if ext == ".docx":
            import docx
            d = docx.Document(str(q))
            parts = [p.text.strip() for p in d.paragraphs if p.text.strip()]
            for tb in d.tables[:3]:
                for row in tb.rows[:8]:
                    parts.append(" | ".join(c.text.strip() for c in row.cells))
            return ("\n".join(parts))[:limit_chars]
        if ext == ".xlsx":
            import openpyxl
            wb = openpyxl.load_workbook(str(q), data_only=True, read_only=True)
            parts = []
            for ws in wb.worksheets[:2]:
                for i, row in enumerate(ws.iter_rows(values_only=True)):
                    if i > 40:
                        break
                    vals = [str(v) for v in row if v not in (None, "")]
                    if vals:
                        parts.append(" | ".join(vals))
            wb.close()
            return ("\n".join(parts))[:limit_chars]
        if ext in (".txt", ".md", ".csv"):
            return q.read_text(encoding="utf-8", errors="ignore")[:limit_chars]
    except Exception:
        return ""
    return ""


# --------------------------------------------------------------------------
#  Сквозная нумерация (как в «прот №лаб №.xlsx»)
# --------------------------------------------------------------------------
NUMBER_KINDS = {
    "protocol": "№ протокола испытаний",
    "lab": "Лабораторный №",
    "ez": "Экспертное заключение",
    "act": "Акт отбора проб",
}
REGISTRY_FILE = "прот №лаб №.xlsx"


def _cell_number(v):
    """Номер из ячейки вида 2878, 2878-2881, 1301.09. Старые форматы с «/» пропускаем."""
    if v is None:
        return None
    s = str(v).strip().replace(" ", "")
    if not s or "/" in s or not any(ch.isdigit() for ch in s):
        return None
    nums = [int(x) for x in __import__("re").findall(r"\d+", s)]
    nums = [n for n in nums if 0 < n < 100000]
    if not nums:
        return None
    if "-" in s:
        return max(nums)
    return nums[0]


def registry_max(path: str | None = None) -> dict:
    """Максимальные номера по каждому виду из реестра «прот №лаб №.xlsx»."""
    import openpyxl
    q = Path(path) if path else (BASE.parent / REGISTRY_FILE)
    if not q.exists():
        return {}
    wb = openpyxl.load_workbook(str(q), data_only=True, read_only=True)
    cols = {"protocol": 0, "lab": 5, "ez": 10, "act": 15}
    out = {}
    try:
        for kind, idx in cols.items():
            mx = 0
            for ws in wb.worksheets:
                if not ws.title.strip().isdigit():
                    continue
                for row in ws.iter_rows(min_col=idx + 1, max_col=idx + 1, values_only=True):
                    n = _cell_number(row[0] if row else None)
                    if n and n > mx:
                        mx = n
            out[kind] = mx
    finally:
        wb.close()
    return out


def numbering_state() -> dict:
    con = connect()
    rows = {r["kind"]: r["next_value"] for r in con.execute("SELECT * FROM numbering")}
    con.close()
    for k in NUMBER_KINDS:
        rows.setdefault(k, 1)
    return rows


def peek_number(kind: str) -> int:
    return int(numbering_state().get(kind, 1))


def take_number(kind: str, doc_type: str = "", doc_id: int | None = None,
                object_name: str = "") -> int:
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute("SELECT next_value FROM numbering WHERE kind=?", (kind,)).fetchone()
        value = int(row["next_value"]) if row else 1
        now = datetime.now().isoformat(timespec="seconds")
        con.execute("INSERT INTO numbering(kind,next_value,updated_at) VALUES (?,?,?) "
                    "ON CONFLICT(kind) DO UPDATE SET next_value=excluded.next_value, updated_at=excluded.updated_at",
                    (kind, value + 1, now))
        con.execute("INSERT INTO number_log(kind,value,doc_type,doc_id,object_name,created_at) "
                    "VALUES (?,?,?,?,?,?)", (kind, value, doc_type, doc_id, object_name, now))
        con.commit()
        return value
    finally:
        con.close()


def set_number(kind: str, value: int) -> None:
    con = connect()
    con.execute("INSERT INTO numbering(kind,next_value,updated_at) VALUES (?,?,?) "
                "ON CONFLICT(kind) DO UPDATE SET next_value=excluded.next_value, updated_at=excluded.updated_at",
                (kind, max(1, int(value)), datetime.now().isoformat(timespec="seconds")))
    con.commit()
    con.close()


def ensure_number_after(kind: str, value) -> None:
    """Если ввели номер вручную — сдвигаем счётчик, чтобы следующий не повторился."""
    try:
        v = int(str(value).strip())
    except (TypeError, ValueError):
        return
    if v >= peek_number(kind):
        set_number(kind, v + 1)


def sync_numbering(path: str | None = None, force: bool = False) -> dict:
    found = registry_max(path)
    con = connect()
    now = datetime.now().isoformat(timespec="seconds")
    for kind, mx in found.items():
        if mx <= 0:
            continue
        row = con.execute("SELECT next_value FROM numbering WHERE kind=?", (kind,)).fetchone()
        nxt = mx + 1
        if row and not force:
            nxt = max(int(row["next_value"]), nxt)
        con.execute("INSERT INTO numbering(kind,next_value,updated_at) VALUES (?,?,?) "
                    "ON CONFLICT(kind) DO UPDATE SET next_value=excluded.next_value, updated_at=excluded.updated_at",
                    (kind, nxt, now))
    con.commit()
    con.close()
    set_setting("numbering_synced_at", now)
    return {"found": found, "next": numbering_state()}


def number_log(limit: int = 40) -> list[dict]:
    con = connect()
    rows = [dict(r) for r in con.execute(
        "SELECT * FROM number_log ORDER BY id DESC LIMIT ?", (limit,))]
    con.close()
    return rows


def add_audit(user: dict | None, action: str, entity: str = "", entity_id: int = 0,
              details: str = "") -> None:
    if not (get_setting("audit", {}) or {}).get("enabled", True):
        return
    con = connect()
    con.execute("INSERT INTO audit_log(ts,user_id,user_name,role,action,entity,entity_id,details)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (datetime.now().isoformat(timespec="seconds"),
                 int((user or {}).get("id") or 0), (user or {}).get("name") or "—",
                 (user or {}).get("role") or "", action, entity, int(entity_id or 0),
                 (details or "")[:500]))
    con.commit()
    con.close()


def audit_list(limit: int = 300, q: str = "") -> list[dict]:
    con = connect()
    con.execute("""CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, user_id INTEGER, user_name TEXT,
        role TEXT, action TEXT, entity TEXT, entity_id INTEGER, details TEXT)""")
    if q:
        rows = con.execute(
            "SELECT * FROM audit_log WHERE user_name LIKE ? OR action LIKE ? OR details LIKE ? "
            "ORDER BY id DESC LIMIT ?", (f"%{q}%", f"%{q}%", f"%{q}%", limit)).fetchall()
    else:
        rows = con.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    con.close()
    return [dict(r) for r in rows]


def _pdf_rel(file_rel: str | None) -> str:
    if not file_rel:
        return ""
    q = (BASE / file_rel).with_suffix(".pdf")
    if q.exists():
        try:
            return str(q.relative_to(BASE))
        except ValueError:
            return ""
    return ""


def state() -> dict:
    con = connect()
    protocols = [dict(r) for r in con.execute(
        "SELECT id,number,lab_no,act_no,pdate,kind,object_name,customer,sample,draft,file,created_at,version "
        "FROM protocols ORDER BY id DESC LIMIT 200")]
    reports = [dict(r) for r in con.execute(
        "SELECT id,number,rdate,date_from,date_to,object_name,customer,contract,file,created_at FROM reports ORDER BY id DESC LIMIT 200")]
    objects = [dict(r) for r in con.execute(
        "SELECT * FROM objects ORDER BY CASE status WHEN 'archive' THEN 1 ELSE 0 END, name")]
    counts = {r["object_id"]: r["c"] for r in con.execute(
        "SELECT object_id, COUNT(*) c FROM entries GROUP BY object_id")}
    doc_counts = {r["object_id"]: r["c"] for r in con.execute(
        "SELECT object_id, COUNT(*) c FROM object_docs GROUP BY object_id")}
    for o in objects:
        o["entries_count"] = counts.get(o["id"], 0)
        o["docs_count"] = doc_counts.get(o["id"], 0)
    recent_entries = entries(limit=40)
    contracts = [dict(r) for r in con.execute("SELECT * FROM contracts ORDER BY cdate DESC")]
    by_contract = {}
    for o in objects:
        by_contract.setdefault(o.get("contract_id") or 0, []).append({"id": o["id"], "name": o["name"]})
    for c in contracts:
        c["objects"] = by_contract.get(c["id"], [])
        c["objects_count"] = len(c["objects"])
    employees = [dict(r) for r in con.execute("SELECT * FROM employees ORDER BY id")]
    con.close()
    for p in protocols:
        p["kind_label"] = DOC_KINDS.get(p["kind"], {}).get("short", p["kind"])
        p["pdf"] = _pdf_rel(p.get("file"))
    for r in reports:
        r["pdf"] = _pdf_rel(r.get("file"))
    return {
        "company": company(),
        "norms": norms(),
        "objects": objects,
        "contracts": contracts,
        "employees": employees,
        "entries": recent_entries,
        "protocols": protocols,
        "reports": reports,
        "kinds": DOC_KINDS,
        "ai": get_setting("ai", {}) or {},
        "numbering": numbering_state(),
        "number_kinds": NUMBER_KINDS,
        "number_log": number_log(20),
        "numbering_synced_at": get_setting("numbering_synced_at", ""),
        "today": date.today().isoformat(),
        "stats": {
            "protocols": len(protocols),
            "reports": len(reports),
            "objects": len(objects),
            "contracts": len(contracts),
            "drafts": sum(1 for p in protocols if p.get("draft")),
        },
    }
