DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS users;

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE,
    age INTEGER,
    balance INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    price DECIMAL(10,2) NOT NULL,
    quantity INTEGER DEFAULT 0
);

CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    total DECIMAL(10,2),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE order_items (
    id SERIAL PRIMARY KEY,
    order_id INTEGER REFERENCES orders(id),
    product_id INTEGER REFERENCES products(id),
    quantity INTEGER,
    price DECIMAL(10,2) NOT NULL
);


INSERT INTO users (name, email, age, balance) VALUES
('Dima', 'dima@example.com', 31, 55000),
('Lena', 'lena@example.com', 30, 15000),
('Alex', 'alex@example.com', 41, 30000);

INSERT INTO products (name, price, quantity) VALUES
('Laptop', 1200.00, 10),
('Phone', 800.00, 20),
('Headphones', 150.00, 50),
('Keyboard', 100.00, 30),
('Mouse', 50.00, 40);


INSERT INTO orders (user_id, total) VALUES
(1, 1350.00),
(2, 950.00),
(3, 3000);


INSERT INTO order_items (order_id, product_id, quantity, price) VALUES
(1, 1, 2, 3000),
(2, 2, 4, 5000),
(3, 3, 6, 15000);
