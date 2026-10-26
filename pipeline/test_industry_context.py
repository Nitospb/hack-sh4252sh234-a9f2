import unittest
import sqlite3
from pathlib import Path
from industry_context import industry_anchors

class IndustryContextTests(unittest.TestCase):
    def software(self,text):
        return 'crosscut_29' in industry_anchors(text,text)
    def retail(self,text):
        return 'services_01' in industry_anchors(text,text)
    def test_policy_programmes_are_not_software(self):
        for text in ['Минсельхоз расширил программу субсидирования фермеров',
                     'Программа государственных гарантий ОМС увеличит зарплату медсестёр',
                     'Инвестиционная программа компании составит 100 млрд рублей',
                     'AstraZeneca разработчик лекарств запускает программу CAR-T терапии']:
            with self.subTest(text=text):self.assertFalse(self.software(text))
    def test_software_positive(self):
        for text in ['Программное обеспечение для компаний','Программирование на PHP: выпуск новой версии',
                     'Новая программа PHP для анализа данных','Разработчик приложений получил инвестиции',
                     'Российские программисты выпустили продукт','Рынок программных продуктов растёт']:
            with self.subTest(text=text):self.assertTrue(self.software(text))
    def test_chips_not_crisps(self):
        self.assertTrue(self.software('Новые чипы для серверов вышли на рынок'))
        self.assertFalse(self.software('Производитель чипсов увеличил выпуск'))
    def test_asset_sales_are_not_retail(self):
        for text in ['Продажа акций банка принесла доход','Продажа государственных активов расширяется',
                     'Торговля ценными бумагами на бирже','Озон в атмосфере изменил концентрацию']:
            with self.subTest(text=text):self.assertFalse(self.retail(text))
    def test_real_problem_articles_not_software(self):
        path=Path(__file__).resolve().parent/'output/ranking.sqlite'
        if not path.exists():self.skipTest('No built sidecar')
        ids=['4462a8ca0e9526ee2f86778034a6c904491b6ab227b46f97e7e1570053ee1902',
             '02cbc11521d33864aaa3f09d280fcd071b95259f7b9d0799a1ae4f7cb74d621a',
             'a5caf634073e22ceffc3cbe7fc91c1232943f6142e0e0759950f834f49db9d29']
        with sqlite3.connect(f'file:{path}?mode=ro',uri=True) as db:
            db.execute('ATTACH DATABASE ? AS source', (str(path.with_name('catalog.sqlite')),))
            for aid in ids:
                self.assertEqual(1,db.execute('SELECT COUNT(*) FROM source.articles WHERE article_id=?',(aid,)).fetchone()[0])
                self.assertEqual(0,db.execute("SELECT COUNT(*) FROM article_industries WHERE article_id=? AND sector_id='crosscut_29'",(aid,)).fetchone()[0])
    def test_retail_positive(self):
        for text in ['Розничные сети открывают магазины','Продажи продуктов питания растут',
                     'Маркетплейсы увеличили оборот','Ozon открыл распределительный центр']:
            with self.subTest(text=text):self.assertTrue(self.retail(text))

if __name__=='__main__':unittest.main()
