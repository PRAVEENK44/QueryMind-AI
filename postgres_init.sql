-- PostgreSQL initialization script for QueryMind AI
-- Creates schema, loads data, and creates read-only user

-- Create read-only role
CREATE ROLE querymind_ro NOINHERIT;
GRANT CONNECT ON DATABASE querymind TO querymind_ro;
GRANT USAGE ON SCHEMA public TO querymind_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO querymind_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO querymind_ro;

-- Create read-write role (for initialization/migration)
CREATE ROLE querymind_rw NOINHERIT;
GRANT CONNECT ON DATABASE querymind TO querymind_rw;
GRANT USAGE, CREATE ON SCHEMA public TO querymind_rw;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO querymind_rw;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO querymind_rw;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO querymind_rw;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO querymind_rw;

-- Create users
CREATE USER querymind_ro_user WITH PASSWORD 'readonly_password_change_in_prod';
CREATE USER querymind_rw_user WITH PASSWORD 'readwrite_password_change_in_prod';

GRANT querymind_ro TO querymind_ro_user;
GRANT querymind_rw TO querymind_rw_user;

-- Set default roles
ALTER USER querymind_ro_user SET ROLE querymind_ro;
ALTER USER querymind_rw_user SET ROLE querymind_rw;

-- HR Tables
CREATE TABLE departments (
    dept_id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    region TEXT,
    budget NUMERIC(12,2)
);

CREATE TABLE employees (
    emp_id SERIAL PRIMARY KEY,
    dept_id INTEGER REFERENCES departments(dept_id),
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    hire_date DATE,
    status TEXT DEFAULT 'Active'
);

CREATE TABLE salaries (
    salary_id SERIAL PRIMARY KEY,
    emp_id INTEGER REFERENCES employees(emp_id),
    base_salary NUMERIC(12,2),
    bonus NUMERIC(12,2),
    effective_date DATE
);

-- CRM & Marketing Tables
CREATE TABLE campaigns (
    campaign_id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    channel TEXT,
    start_date DATE,
    end_date DATE,
    budget NUMERIC(12,2),
    roi_percent NUMERIC(6,2)
);

CREATE TABLE customers (
    customer_id SERIAL PRIMARY KEY,
    company_name TEXT NOT NULL,
    industry TEXT,
    campaign_source_id INTEGER REFERENCES campaigns(campaign_id),
    total_ltv NUMERIC(14,2) DEFAULT 0
);

CREATE TABLE interactions (
    interaction_id SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(customer_id),
    emp_id INTEGER REFERENCES employees(emp_id),
    type TEXT,
    date DATE,
    sentiment_score NUMERIC(4,2)
);

-- Supply Chain Tables
CREATE TABLE warehouses (
    warehouse_id SERIAL PRIMARY KEY,
    location TEXT NOT NULL,
    capacity INTEGER,
    manager_emp_id INTEGER REFERENCES employees(emp_id)
);

CREATE TABLE suppliers (
    supplier_id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    country TEXT,
    rating NUMERIC(3,2)
);

CREATE TABLE products (
    product_id SERIAL PRIMARY KEY,
    supplier_id INTEGER REFERENCES suppliers(supplier_id),
    name TEXT NOT NULL,
    category TEXT,
    unit_cost NUMERIC(12,2),
    msrp NUMERIC(12,2)
);

CREATE TABLE inventory (
    inventory_id SERIAL PRIMARY KEY,
    warehouse_id INTEGER REFERENCES warehouses(warehouse_id),
    product_id INTEGER REFERENCES products(product_id),
    quantity_on_hand INTEGER,
    restock_threshold INTEGER
);

-- Sales & Finance Tables
CREATE TABLE orders (
    order_id SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(customer_id),
    sales_rep_emp_id INTEGER REFERENCES employees(emp_id),
    date DATE,
    total_amount NUMERIC(12,2),
    status TEXT DEFAULT 'Processing'
);

CREATE TABLE order_items (
    item_id SERIAL PRIMARY KEY,
    order_id INTEGER REFERENCES orders(order_id),
    product_id INTEGER REFERENCES products(product_id),
    quantity INTEGER,
    subtotal NUMERIC(12,2)
);

CREATE TABLE shipments (
    shipment_id SERIAL PRIMARY KEY,
    order_id INTEGER REFERENCES orders(order_id),
    warehouse_id INTEGER REFERENCES warehouses(warehouse_id),
    dispatch_date DATE,
    delivery_date DATE,
    status TEXT
);

CREATE TABLE invoices (
    invoice_id SERIAL PRIMARY KEY,
    order_id INTEGER REFERENCES orders(order_id),
    issue_date DATE,
    due_date DATE,
    paid_date DATE,
    status TEXT DEFAULT 'Pending',
    amount NUMERIC(12,2)
);

-- Create indexes for performance
CREATE INDEX idx_employees_dept_id ON employees(dept_id);
CREATE INDEX idx_salaries_emp_id ON salaries(emp_id);
CREATE INDEX idx_customers_campaign_source ON customers(campaign_source_id);
CREATE INDEX idx_interactions_customer_id ON interactions(customer_id);
CREATE INDEX idx_interactions_emp_id ON interactions(emp_id);
CREATE INDEX idx_products_supplier_id ON products(supplier_id);
CREATE INDEX idx_inventory_warehouse ON inventory(warehouse_id);
CREATE INDEX idx_inventory_product ON inventory(product_id);
CREATE INDEX idx_orders_customer ON orders(customer_id);
CREATE INDEX idx_orders_sales_rep ON orders(sales_rep_emp_id);
CREATE INDEX idx_order_items_order ON order_items(order_id);
CREATE INDEX idx_order_items_product ON order_items(product_id);
CREATE INDEX idx_shipments_order ON shipments(order_id);
CREATE INDEX idx_shipments_warehouse ON shipments(warehouse_id);
CREATE INDEX idx_invoices_order ON invoices(order_id);