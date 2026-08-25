"""Database setup and initialization (Enterprise Corporate Edition)."""

import os
import random
import sqlite3
from datetime import datetime, timedelta


def get_db_path():
    return os.path.join(os.path.dirname(__file__), "..", "querymind.db")


def init_database():
    """Initialize the massive 14-table corporate database with interrelated synthetic data."""
    db_path = get_db_path()

    # We will conditionally drop and rebuild to ensure schema is fresh if user requested a bigger DB
    # However to be safe against random restarts, we check for 'departments'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='departments'")
    if cursor.fetchone():
        cursor.execute("SELECT COUNT(*) FROM departments")
        if cursor.fetchone()[0] > 0:
            conn.close()
            return  # Already initialized

    print("Generating Massive Corporate Dataset...", flush=True)

    # Enable foreign keys
    cursor.execute("PRAGMA foreign_keys = ON;")

    # ---------------------------------------------------------
    # DOMAIN 1: HR
    # ---------------------------------------------------------
    cursor.execute("""CREATE TABLE IF NOT EXISTS departments (
        dept_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT, region TEXT, budget REAL)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS employees (
        emp_id INTEGER PRIMARY KEY AUTOINCREMENT,
        dept_id INTEGER, first_name TEXT, last_name TEXT,
        hire_date TEXT, status TEXT,
        FOREIGN KEY(dept_id) REFERENCES departments(dept_id))""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS salaries (
        salary_id INTEGER PRIMARY KEY AUTOINCREMENT,
        emp_id INTEGER, base_salary REAL, bonus REAL, effective_date TEXT,
        FOREIGN KEY(emp_id) REFERENCES employees(emp_id))""")

    # ---------------------------------------------------------
    # DOMAIN 2: CRM & MARKETING
    # ---------------------------------------------------------
    cursor.execute("""CREATE TABLE IF NOT EXISTS campaigns (
        campaign_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT, channel TEXT, start_date TEXT, end_date TEXT, budget REAL, roi_percent REAL)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS customers (
        customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_name TEXT, industry TEXT, campaign_source_id INTEGER, total_ltv REAL,
        FOREIGN KEY(campaign_source_id) REFERENCES campaigns(campaign_id))""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS interactions (
        interaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER, emp_id INTEGER, type TEXT, date TEXT, sentiment_score REAL,
        FOREIGN KEY(customer_id) REFERENCES customers(customer_id),
        FOREIGN KEY(emp_id) REFERENCES employees(emp_id))""")

    # ---------------------------------------------------------
    # DOMAIN 3: LOGISTICS & SUPPLY CHAIN
    # ---------------------------------------------------------
    cursor.execute("""CREATE TABLE IF NOT EXISTS warehouses (
        warehouse_id INTEGER PRIMARY KEY AUTOINCREMENT,
        location TEXT, capacity INTEGER, manager_emp_id INTEGER,
        FOREIGN KEY(manager_emp_id) REFERENCES employees(emp_id))""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS suppliers (
        supplier_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT, country TEXT, rating REAL)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS products (
        product_id INTEGER PRIMARY KEY AUTOINCREMENT,
        supplier_id INTEGER, name TEXT, category TEXT, unit_cost REAL, msrp REAL,
        FOREIGN KEY(supplier_id) REFERENCES suppliers(supplier_id))""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS inventory (
        inventory_id INTEGER PRIMARY KEY AUTOINCREMENT,
        warehouse_id INTEGER, product_id INTEGER, quantity_on_hand INTEGER, restock_threshold INTEGER,
        FOREIGN KEY(warehouse_id) REFERENCES warehouses(warehouse_id),
        FOREIGN KEY(product_id) REFERENCES products(product_id))""")

    # ---------------------------------------------------------
    # DOMAIN 4: SALES & FINANCE
    # ---------------------------------------------------------
    cursor.execute("""CREATE TABLE IF NOT EXISTS orders (
        order_id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER, sales_rep_emp_id INTEGER, date TEXT, total_amount REAL, status TEXT,
        FOREIGN KEY(customer_id) REFERENCES customers(customer_id),
        FOREIGN KEY(sales_rep_emp_id) REFERENCES employees(emp_id))""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS order_items (
        item_id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER, product_id INTEGER, quantity INTEGER, subtotal REAL,
        FOREIGN KEY(order_id) REFERENCES orders(order_id),
        FOREIGN KEY(product_id) REFERENCES products(product_id))""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS shipments (
        shipment_id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER, warehouse_id INTEGER, dispatch_date TEXT, delivery_date TEXT, status TEXT,
        FOREIGN KEY(order_id) REFERENCES orders(order_id),
        FOREIGN KEY(warehouse_id) REFERENCES warehouses(warehouse_id))""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS invoices (
        invoice_id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER, issue_date TEXT, due_date TEXT, paid_date TEXT, status TEXT, amount REAL,
        FOREIGN KEY(order_id) REFERENCES orders(order_id))""")

    # ---------------------------------------------------------
    # DATA GENERATION (BULK)
    # ---------------------------------------------------------
    conn.execute("BEGIN TRANSACTION")

    # HR Data
    depts = [
        ("Engineering", "NAMER", 5000000),
        ("Sales", "EMEA", 3000000),
        ("Marketing", "APAC", 2000000),
        ("Support", "NAMER", 1500000),
    ]
    cursor.executemany("INSERT INTO departments (name, region, budget) VALUES (?, ?, ?)", depts)
    dept_ids = [1, 2, 3, 4]

    first_names = [
        "James",
        "Mary",
        "Robert",
        "Patricia",
        "John",
        "Jennifer",
        "Michael",
        "Linda",
        "William",
        "Elizabeth",
        "David",
        "Barbara",
        "Richard",
        "Susan",
        "Joseph",
        "Jessica",
        "Thomas",
        "Sarah",
        "Charles",
        "Karen",
    ]
    last_names = [
        "Smith",
        "Johnson",
        "Williams",
        "Brown",
        "Jones",
        "Garcia",
        "Miller",
        "Davis",
        "Rodriguez",
        "Martinez",
        "Hernandez",
        "Lopez",
        "Gonzalez",
        "Wilson",
        "Anderson",
        "Thomas",
        "Taylor",
        "Moore",
        "Jackson",
        "Martin",
    ]

    emp_data = []
    sal_data = []
    for i in range(1, 151):  # 150 employees
        d_id = random.choice(dept_ids)
        h_date = (datetime.now() - timedelta(days=random.randint(100, 2000))).strftime("%Y-%m-%d")
        emp_data.append(
            (d_id, random.choice(first_names), random.choice(last_names), h_date, "Active")
        )
        base = random.uniform(60000, 150000)
        sal_data.append((i, base, base * random.uniform(0.05, 0.2), h_date))

    cursor.executemany(
        "INSERT INTO employees (dept_id, first_name, last_name, hire_date, status) VALUES (?, ?, ?, ?, ?)",
        emp_data,
    )
    cursor.executemany(
        "INSERT INTO salaries (emp_id, base_salary, bonus, effective_date) VALUES (?, ?, ?, ?)",
        sal_data,
    )

    # Marketing & CRM
    camp_data = [
        ("Q1 Performance", "LinkedIn", "2025-01-01", "2025-03-31", 50000, 120),
        ("SaaS Expansion", "Google Ads", "2025-04-01", "2025-06-30", 120000, 210),
        ("Winter Cloud Event", "Email", "2024-11-01", "2024-12-31", 30000, 85),
        ("Enterprise Summit", "Event", "2025-02-15", "2025-02-20", 250000, 340),
    ]
    cursor.executemany(
        "INSERT INTO campaigns (name, channel, start_date, end_date, budget, roi_percent) VALUES (?, ?, ?, ?, ?, ?)",
        camp_data,
    )

    industries = ["Finance", "Healthcare", "Tech", "Manufacturing", "Retail"]
    cust_data = []
    for i in range(1, 401):  # 400 Customers
        c_id = random.randint(1, 4)
        cust_data.append((f"CorpEntity {i} LLC", random.choice(industries), c_id, 0))
    cursor.executemany(
        "INSERT INTO customers (company_name, industry, campaign_source_id, total_ltv) VALUES (?, ?, ?, ?)",
        cust_data,
    )

    # Interactions (2000 records)
    int_data = []
    for _ in range(2000):
        c_id = random.randint(1, 400)
        e_id = random.randint(1, 150)
        date = (datetime.now() - timedelta(days=random.randint(1, 365))).strftime("%Y-%m-%d")
        int_data.append(
            (
                c_id,
                e_id,
                random.choice(["Call", "Email", "Ticket"]),
                date,
                random.uniform(1.0, 10.0),
            )
        )
    cursor.executemany(
        "INSERT INTO interactions (customer_id, emp_id, type, date, sentiment_score) VALUES (?, ?, ?, ?, ?)",
        int_data,
    )

    # Logistics & Products
    wh_data = [
        ("New York Hub", 50000, 10),
        ("London Central", 45000, 20),
        ("Tokyo Apex", 30000, 30),
    ]
    cursor.executemany(
        "INSERT INTO warehouses (location, capacity, manager_emp_id) VALUES (?, ?, ?)", wh_data
    )

    sup_data = [
        ("GlobalTech", "USA", 4.8),
        ("EuroParts", "Germany", 4.5),
        ("AsiaChips", "Taiwan", 4.9),
    ]
    cursor.executemany("INSERT INTO suppliers (name, country, rating) VALUES (?, ?, ?)", sup_data)

    prod_data = []
    for i in range(1, 51):  # 50 products
        s_id = random.randint(1, 3)
        cost = random.uniform(500, 5000)
        prod_data.append((s_id, f"Enterprise Server Gen{i}", "Hardware", cost, cost * 1.6))
    cursor.executemany(
        "INSERT INTO products (supplier_id, name, category, unit_cost, msrp) VALUES (?, ?, ?, ?, ?)",
        prod_data,
    )

    inv_data = []
    for p_id in range(1, 51):
        for w_id in range(1, 4):
            inv_data.append((w_id, p_id, random.randint(50, 1000), 100))
    cursor.executemany(
        "INSERT INTO inventory (warehouse_id, product_id, quantity_on_hand, restock_threshold) VALUES (?, ?, ?, ?)",
        inv_data,
    )

    # Sales & Invoices (3000 orders)
    sales_reps = [i for i in range(1, 151) if i % 2 == 0]  # Assume evens are sales

    order_data = []
    item_data = []
    ship_data = []
    inv_docs = []
    customer_ltv = dict.fromkeys(range(1, 401), 0)

    # Pre-fetch MSRP to calculate subtotals
    cursor.execute("SELECT product_id, msrp FROM products")
    price_map = dict(cursor.fetchall())

    item_id_counter = 1
    for o_id in range(1, 3001):
        c_id = random.randint(1, 400)
        s_rep = random.choice(sales_reps)
        date_obj = datetime.now() - timedelta(days=random.randint(1, 700))
        date = date_obj.strftime("%Y-%m-%d")

        status = random.choice(["Completed", "Completed", "Completed", "Processing", "Cancelled"])
        order_total = 0

        # Items
        for _ in range(random.randint(1, 5)):
            p_id = random.randint(1, 50)
            qty = random.randint(1, 10)
            subtotal = price_map[p_id] * qty
            order_total += subtotal
            item_data.append((o_id, p_id, qty, subtotal))
            item_id_counter += 1

        customer_ltv[c_id] += order_total
        order_data.append((c_id, s_rep, date, order_total, status))

        # Shipments (if not cancelled)
        if status != "Cancelled":
            w_id = random.randint(1, 3)
            d_date = (date_obj + timedelta(days=random.randint(1, 3))).strftime("%Y-%m-%d")
            del_date = (
                (date_obj + timedelta(days=random.randint(4, 10))).strftime("%Y-%m-%d")
                if status == "Completed"
                else None
            )
            ship_data.append(
                (
                    o_id,
                    w_id,
                    d_date,
                    del_date,
                    "Delivered" if status == "Completed" else "In Transit",
                )
            )

        # Invoices
        due = (date_obj + timedelta(days=30)).strftime("%Y-%m-%d")
        paid = (
            (date_obj + timedelta(days=random.randint(5, 45))).strftime("%Y-%m-%d")
            if status == "Completed"
            else None
        )
        inv_docs.append((o_id, date, due, paid, "Paid" if paid else "Pending", order_total))

    cursor.executemany(
        "INSERT INTO orders (customer_id, sales_rep_emp_id, date, total_amount, status) VALUES (?, ?, ?, ?, ?)",
        order_data,
    )
    cursor.executemany(
        "INSERT INTO order_items (order_id, product_id, quantity, subtotal) VALUES (?, ?, ?, ?)",
        item_data,
    )
    cursor.executemany(
        "INSERT INTO shipments (order_id, warehouse_id, dispatch_date, delivery_date, status) VALUES (?, ?, ?, ?, ?)",
        ship_data,
    )
    cursor.executemany(
        "INSERT INTO invoices (order_id, issue_date, due_date, paid_date, status, amount) VALUES (?, ?, ?, ?, ?, ?)",
        inv_docs,
    )

    # Bulk update customer LTV
    ltv_updates = [(total, c_id) for c_id, total in customer_ltv.items()]
    cursor.executemany("UPDATE customers SET total_ltv = ? WHERE customer_id = ?", ltv_updates)

    conn.commit()
    conn.close()
    print("Massive Generative Seed Complete.", flush=True)


def get_schema():
    """Return the vast enterprise schema topology."""
    return {
        "tables": {
            "departments": {
                "columns": {
                    "dept_id": "INTEGER",
                    "name": "TEXT",
                    "region": "TEXT",
                    "budget": "REAL",
                }
            },
            "employees": {
                "columns": {
                    "emp_id": "INTEGER",
                    "dept_id": "INTEGER",
                    "first_name": "TEXT",
                    "last_name": "TEXT",
                    "hire_date": "TEXT",
                    "status": "TEXT",
                }
            },
            "salaries": {
                "columns": {
                    "salary_id": "INTEGER",
                    "emp_id": "INTEGER",
                    "base_salary": "REAL",
                    "bonus": "REAL",
                    "effective_date": "TEXT",
                }
            },
            "campaigns": {
                "columns": {
                    "campaign_id": "INTEGER",
                    "name": "TEXT",
                    "channel": "TEXT",
                    "start_date": "TEXT",
                    "end_date": "TEXT",
                    "budget": "REAL",
                    "roi_percent": "REAL",
                }
            },
            "customers": {
                "columns": {
                    "customer_id": "INTEGER",
                    "company_name": "TEXT",
                    "industry": "TEXT",
                    "campaign_source_id": "INTEGER",
                    "total_ltv": "REAL",
                }
            },
            "interactions": {
                "columns": {
                    "interaction_id": "INTEGER",
                    "customer_id": "INTEGER",
                    "emp_id": "INTEGER",
                    "type": "TEXT",
                    "date": "TEXT",
                    "sentiment_score": "REAL",
                }
            },
            "warehouses": {
                "columns": {
                    "warehouse_id": "INTEGER",
                    "location": "TEXT",
                    "capacity": "INTEGER",
                    "manager_emp_id": "INTEGER",
                }
            },
            "suppliers": {
                "columns": {
                    "supplier_id": "INTEGER",
                    "name": "TEXT",
                    "country": "TEXT",
                    "rating": "REAL",
                }
            },
            "products": {
                "columns": {
                    "product_id": "INTEGER",
                    "supplier_id": "INTEGER",
                    "name": "TEXT",
                    "category": "TEXT",
                    "unit_cost": "REAL",
                    "msrp": "REAL",
                }
            },
            "inventory": {
                "columns": {
                    "inventory_id": "INTEGER",
                    "warehouse_id": "INTEGER",
                    "product_id": "INTEGER",
                    "quantity_on_hand": "INTEGER",
                    "restock_threshold": "INTEGER",
                }
            },
            "orders": {
                "columns": {
                    "order_id": "INTEGER",
                    "customer_id": "INTEGER",
                    "sales_rep_emp_id": "INTEGER",
                    "date": "TEXT",
                    "total_amount": "REAL",
                    "status": "TEXT",
                }
            },
            "order_items": {
                "columns": {
                    "item_id": "INTEGER",
                    "order_id": "INTEGER",
                    "product_id": "INTEGER",
                    "quantity": "INTEGER",
                    "subtotal": "REAL",
                }
            },
            "shipments": {
                "columns": {
                    "shipment_id": "INTEGER",
                    "order_id": "INTEGER",
                    "warehouse_id": "INTEGER",
                    "dispatch_date": "TEXT",
                    "delivery_date": "TEXT",
                    "status": "TEXT",
                }
            },
            "invoices": {
                "columns": {
                    "invoice_id": "INTEGER",
                    "order_id": "INTEGER",
                    "issue_date": "TEXT",
                    "due_date": "TEXT",
                    "paid_date": "TEXT",
                    "status": "TEXT",
                    "amount": "REAL",
                }
            },
        },
        "term_mappings": {
            "sales": "total_amount",
            "revenue": "total_amount",
            "client": "customer_id",
            "staff": "emp_id",
            "stock": "quantity_on_hand",
            "location": "region",
        },
        "relationships": [
            {
                "from_table": "employees",
                "from_col": "dept_id",
                "to_table": "departments",
                "to_col": "dept_id",
            },
            {
                "from_table": "salaries",
                "from_col": "emp_id",
                "to_table": "employees",
                "to_col": "emp_id",
            },
            {
                "from_table": "customers",
                "from_col": "campaign_source_id",
                "to_table": "campaigns",
                "to_col": "campaign_id",
            },
            {
                "from_table": "interactions",
                "from_col": "customer_id",
                "to_table": "customers",
                "to_col": "customer_id",
            },
            {
                "from_table": "interactions",
                "from_col": "emp_id",
                "to_table": "employees",
                "to_col": "emp_id",
            },
            {
                "from_table": "warehouses",
                "from_col": "manager_emp_id",
                "to_table": "employees",
                "to_col": "emp_id",
            },
            {
                "from_table": "products",
                "from_col": "supplier_id",
                "to_table": "suppliers",
                "to_col": "supplier_id",
            },
            {
                "from_table": "inventory",
                "from_col": "warehouse_id",
                "to_table": "warehouses",
                "to_col": "warehouse_id",
            },
            {
                "from_table": "inventory",
                "from_col": "product_id",
                "to_table": "products",
                "to_col": "product_id",
            },
            {
                "from_table": "orders",
                "from_col": "customer_id",
                "to_table": "customers",
                "to_col": "customer_id",
            },
            {
                "from_table": "orders",
                "from_col": "sales_rep_emp_id",
                "to_table": "employees",
                "to_col": "emp_id",
            },
            {
                "from_table": "order_items",
                "from_col": "order_id",
                "to_table": "orders",
                "to_col": "order_id",
            },
            {
                "from_table": "order_items",
                "from_col": "product_id",
                "to_table": "products",
                "to_col": "product_id",
            },
            {
                "from_table": "shipments",
                "from_col": "order_id",
                "to_table": "orders",
                "to_col": "order_id",
            },
            {
                "from_table": "shipments",
                "from_col": "warehouse_id",
                "to_table": "warehouses",
                "to_col": "warehouse_id",
            },
            {
                "from_table": "invoices",
                "from_col": "order_id",
                "to_table": "orders",
                "to_col": "order_id",
            },
        ],
    }
