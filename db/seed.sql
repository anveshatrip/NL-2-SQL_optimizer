

CREATE TABLE users (
    id          SERIAL PRIMARY KEY,
    name        TEXT        NOT NULL,
    email       TEXT        UNIQUE NOT NULL,
    country     TEXT,
    created_at  TIMESTAMP   DEFAULT NOW()
);

CREATE TABLE products (
    id          SERIAL PRIMARY KEY,
    name        TEXT            NOT NULL,
    category    TEXT,
    price       DECIMAL(10,2),
    stock       INT             DEFAULT 0
);

CREATE TABLE orders (
    id          SERIAL PRIMARY KEY,
    user_id     INT             REFERENCES users(id),
    status      TEXT            DEFAULT 'pending',
    total       DECIMAL(10,2),
    created_at  TIMESTAMP       DEFAULT NOW()
);

CREATE TABLE order_items (
    id          SERIAL PRIMARY KEY,
    order_id    INT             REFERENCES orders(id),
    product_id  INT             REFERENCES products(id),
    quantity    INT,
    unit_price  DECIMAL(10,2)
);

CREATE TABLE reviews (
    id          SERIAL PRIMARY KEY,
    user_id     INT             REFERENCES users(id),
    product_id  INT             REFERENCES products(id),
    rating      INT             CHECK (rating BETWEEN 1 AND 5),
    body        TEXT,
    created_at  TIMESTAMP       DEFAULT NOW()
);

-- ── Indexes (intentionally partial to trigger anti-pattern detection) ─────────
-- products.category indexed (good)
CREATE INDEX idx_products_category ON products(category);

-- ── Seed Data ─────────────────────────────────────────────────────────────────

-- Users: 500 rows
INSERT INTO users (name, email, country, created_at)
SELECT
    'User_' || i,
    'user_' || i || '@example.com',
    (ARRAY['India','USA','UK','Germany','France','Brazil','Canada','Japan'])[1 + (i % 8)],
    NOW() - ((random() * 730)::INT || ' days')::INTERVAL
FROM generate_series(1, 500) AS i;

-- Products: 200 rows
INSERT INTO products (name, category, price, stock)
SELECT
    'Product_' || i,
    (ARRAY['Electronics','Clothing','Books','Food','Sports','Toys','Beauty','Home'])[1 + (i % 8)],
    ROUND((random() * 495 + 5)::NUMERIC, 2),
    (random() * 200)::INT
FROM generate_series(1, 200) AS i;

-- Orders: 1500 rows
INSERT INTO orders (user_id, status, total, created_at)
SELECT
    1 + (random() * 499)::INT,
    (ARRAY['pending','shipped','delivered','cancelled'])[1 + (random() * 3)::INT],
    ROUND((random() * 980 + 20)::NUMERIC, 2),
    NOW() - ((random() * 365)::INT || ' days')::INTERVAL
FROM generate_series(1, 1500) AS i;

-- Order items: 4500 rows
INSERT INTO order_items (order_id, product_id, quantity, unit_price)
SELECT
    1 + (random() * 1499)::INT,
    1 + (random() * 199)::INT,
    1 + (random() * 5)::INT,
    ROUND((random() * 195 + 5)::NUMERIC, 2)
FROM generate_series(1, 4500) AS i;

-- Reviews: 800 rows
INSERT INTO reviews (user_id, product_id, rating, body, created_at)
SELECT
    1 + (random() * 499)::INT,
    1 + (random() * 199)::INT,
    1 + (random() * 4)::INT,
    'This is review number ' || i || '. Great product overall.',
    NOW() - ((random() * 365)::INT || ' days')::INTERVAL
FROM generate_series(1, 800) AS i;
