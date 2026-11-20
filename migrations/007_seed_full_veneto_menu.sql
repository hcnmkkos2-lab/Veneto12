BEGIN;

UPDATE business_settings SET value='فنيتو للحلويات والكيك والمعجنات' WHERE key='business_name_ar';
UPDATE business_settings SET value='فينيتو' WHERE key='business_name';

DELETE FROM product_variants;
DELETE FROM product_images;
DELETE FROM products;
DELETE FROM product_categories;

INSERT INTO product_categories (id,name_ar,slug,image_url,sort_order,active,created_at)
VALUES
  (1,'الحلويات','sweets','',1,1,strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  (2,'المعجنات والكيك','pastries-cakes','',2,1,strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  (3,'ورق عنب','stuffed-grape-leaves','',3,1,strftime('%Y-%m-%dT%H:%M:%SZ','now'));

INSERT INTO products (category_id,name_ar,description_ar,price_iqd,available,featured,is_new,sort_order,created_at,updated_at)
VALUES
  (1,'طبق السعادة حجم وسط','نكهات تصنع يومك سعادة',3000,1,1,0,1,strftime('%Y-%m-%dT%H:%M:%SZ','now'),strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  (1,'طبق السعادة حجم كبير بالنوتيلا','كل لقمة حكاية سعادة',4000,1,1,0,2,strftime('%Y-%m-%dT%H:%M:%SZ','now'),strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  (1,'طبق السعادة حجم كبير باللوتس أو بستاشيو','حلويات فينيتو الطازجة',5000,1,1,0,3,strftime('%Y-%m-%dT%H:%M:%SZ','now'),strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  (1,'كيكة بركانية مني','كيكة شهية جاهزة لك',3000,1,0,1,4,strftime('%Y-%m-%dT%H:%M:%SZ','now'),strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  (1,'سنيكرز','حلاوة طازجة من فينيتو',1500,1,0,0,5,strftime('%Y-%m-%dT%H:%M:%SZ','now'),strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  (1,'دسباسيتو','حلوى جاهزة وبنكهات فاخرة',15000,1,1,0,6,strftime('%Y-%m-%dT%H:%M:%SZ','now'),strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  (1,'سكوب كوكيز','تشكيلة كوكيز طازجة',3000,1,0,1,7,strftime('%Y-%m-%dT%H:%M:%SZ','now'),strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  (1,'كوكيز طري','قطعة كوكيز طازجة',1500,1,0,0,8,strftime('%Y-%m-%dT%H:%M:%SZ','now'),strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  (1,'كيك كرانشي','كيك مقرمش بطعم غني',3000,1,0,0,9,strftime('%Y-%m-%dT%H:%M:%SZ','now'),strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  (1,'لافا كيك','كيك ساخن بطعم فاخر',4000,1,1,0,10,strftime('%Y-%m-%dT%H:%M:%SZ','now'),strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  (1,'كيك بيتي','كيكة بيتي جاهزة لك',5000,1,0,0,11,strftime('%Y-%m-%dT%H:%M:%SZ','now'),strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  (1,'لقيمات كاستر بالنوتيلا','لقيمات طازجة بالنوتيلا',2000,1,0,1,12,strftime('%Y-%m-%dT%H:%M:%SZ','now'),strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  (1,'لقيمات لوتس','لقيمات طازجة بلوتس',1500,1,0,0,13,strftime('%Y-%m-%dT%H:%M:%SZ','now'),strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  (1,'قدح لوتس ، بستاشيو ، أوريو','تشكيلة قدح فاخرة',1500,1,0,0,14,strftime('%Y-%m-%dT%H:%M:%SZ','now'),strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  (1,'كريم بف قطعة','كريم بف طازج',500,1,0,0,15,strftime('%Y-%m-%dT%H:%M:%SZ','now'),strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  (1,'كيكة دبي','كيكة دبي الشهية',3000,1,1,0,16,strftime('%Y-%m-%dT%H:%M:%SZ','now'),strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  (1,'دونات قطعة','دونات طازجة قطعة واحدة',500,1,0,0,17,strftime('%Y-%m-%dT%H:%M:%SZ','now'),strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  (2,'كيلو ماكنتوش','معجنات طازجة بالكيلو',13000,1,1,0,18,strftime('%Y-%m-%dT%H:%M:%SZ','now'),strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  (2,'كيلو برازق','برازق طازج بالكيلو',12000,1,1,0,19,strftime('%Y-%m-%dT%H:%M:%SZ','now'),strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  (2,'كيلو كعب الغزال','كعب غزال طازج بالكيلو',12000,1,0,0,20,strftime('%Y-%m-%dT%H:%M:%SZ','now'),strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  (2,'كيلو كوكيز','كوكيز طازج بالكيلو',12000,1,0,1,21,strftime('%Y-%m-%dT%H:%M:%SZ','now'),strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  (2,'كيلو كليجة مشكل تمر وحلقوم','كليجة مشكل طازجة بالكيلو',10000,1,0,0,22,strftime('%Y-%m-%dT%H:%M:%SZ','now'),strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  (2,'ايس كيك','ايس كيك طازج',2000,1,0,1,23,strftime('%Y-%m-%dT%H:%M:%SZ','now'),strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  (3,'ورق عنب','ورق عنب جاهز للتقديم',5000,1,1,0,24,strftime('%Y-%m-%dT%H:%M:%SZ','now'),strftime('%Y-%m-%dT%H:%M:%SZ','now'));

COMMIT;
