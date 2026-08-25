#!/usr/bin/env python3
"""Load synthetic data into PostgreSQL for QueryMind AI."""
import random
from datetime import datetime, timedelta

import psycopg2
from psycopg2.extras import execute_batch


def get_connection(dbname="querymind", user="querymind_rw_user", password="readwrite_password_change_in_prod", host="localhost", port=5432):
    """Get PostgreSQL connection."""
    return psycopg2.connect(
        dbname=dbname, user=user, password=password, host=host, port=port
    )


def load_data():
    """Load all synthetic data."""
    conn = get_connection()
    conn.autocommit = False
    cur = conn.cursor()

    try:
        print("Loading departments...")
        depts = [
            ("Engineering", "NAMER", 5000000),
            ("Sales", "EMEA", 3000000),
            ("Marketing", "APAC", 2000000),
            ("Support", "NAMER", 1500000),
        ]
        execute_batch(cur, "INSERT INTO departments (name, region, budget) VALUES (%s, %s, %s)", depts)

        print("Loading employees and salaries...")
        first_names = ["James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda", "William", "Elizabeth",
                       "David", "Barbara", "Richard", "Susan", "Joseph", "Jessica", "Thomas", "Sarah", "Charles", "Karen"]
        last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez",
                      "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin"]

        emp_data = []
        for i in range(1, 151):
            d_id = random.randint(1, 4)
            h_date = (datetime.now() - timedelta(days=random.randint(100, 2000))).date()
            emp_data.append((d_id, random.choice(first_names), random.choice(last_names), h_date, "Active"))

        execute_batch(cur, """INSERT INTO employees (dept_id, first_name, last_name, hire_date, status) 
                             VALUES (%s, %s, %s, %s, %s)""", emp_data)

        # Get employee IDs
        cur.execute("SELECT emp_id, hire_date FROM employees ORDER BY emp_id")
        emp_rows = cur.fetchall()

        sal_data = []
        for emp_id, hire_date in emp_rows:
            base = round(random.uniform(60000, 150000), 2)
            bonus = round(base * random.uniform(0.05, 0.2), 2)
            sal_data.append((emp_id, base, bonus, hire_date))

        execute_batch(cur, """INSERT INTO salaries (emp_id, base_salary, bonus, effective_date) 
                             VALUES (%s, %s, %s, %s)""", sal_data)

        print("Loading campaigns...")
        camp_data = [
            ("Q1 Performance", "LinkedIn", "2025-01-01", "2025-03-31", 50000, 120),
            ("SaaS Expansion", "Google Ads", "2025-04-01", "2025-06-30", 120000, 210),
            ("Winter Cloud Event", "Email", "2024-11-01", "2024-12-31", 30000, 85),
            ("Enterprise Summit", "Event", "2025-02-15", "2025-02-20", 250000, 340),
        ]
        execute_batch(cur, """INSERT INTO campaigns (name, channel, start_date, end_date, budget, roi_percent) 
                             VALUES (%s, %s, %s, %s, %s, %s)""", camp_data)

        print("Loading customers...")
        industries = ["Finance", "Healthcare", "Tech", "Manufacturing", "Retail"]
        cust_data = []
        for i in range(1, 401):
            c_id = random.randint(1, 4)
            cust_data.append((f"CorpEntity {i} LLC", random.choice(industries), c_id, 0))
        execute_batch(cur, """INSERT INTO customers (company_name, industry, campaign_source_id, total_ltv) 
                             VALUES (%s, %s, %s, %s)""", cust_data)

        print("Loading interactions...")
        int_data = []
        for _ in range(2000):
            c_id = random.randint(1, 400)
            e_id = random.randint(1, 150)
            date = (datetime.now() - timedelta(days=random.randint(1, 365))).date()
            int_data.append((c_id, e_id, random.choice(["Call", "Email", "Ticket"]), date, round(random.uniform(1.0, 10.0), 2)))
        execute_batch(cur, """INSERT INTO interactions (customer_id, emp_id, type, date, sentiment_score) 
                             VALUES (%s, %s, %s, %s, %s)""", int_data)

        print("Loading warehouses...")
        wh_data = [("New York Hub", 50000, 10), ("London Central", 45000, 20), ("Tokyo Apex", 30000, 30)]
        execute_batch(cur, "INSERT INTO warehouses (location, capacity, manager_emp_id) VALUES (%s, %s, %s)", wh_data)

        print("Loading suppliers...")
        sup_data = [("GlobalTech", "USA", 4.8), ("EuroParts", "Germany", 4.5), ("AsiaChips", "Taiwan", 4.9)]
        execute_batch(cur, "INSERT INTO suppliers (name, country, rating) VALUES (%s, %s, %s)", sup_data)

        print("Loading products...")
        prod_data = []
        for i in range(1, 51):
            s_id = random.randint(1, 3)
            cost = round(random.uniform(500, 5000), 2)
            prod_data.append((s_id, f"Enterprise Server Gen{i}", "Hardware", cost, round(cost * 1.6, 2)))
        execute_batch(cur, """INSERT INTO products (supplier_id, name, category, unit_cost, msrp) 
                             VALUES (%s, %s, %s, %s, %s)""", prod_data)

        print("Loading inventory...")
        inv_data = []
        for p_id in range(1, 51):
            for w_id in range(1, 4):
                inv_data.append((w_id, p_id, random.randint(50, 1000), 100))
        execute_batch(cur, """INSERT INTO inventory (warehouse_id, product_id, quantity_on_hand, restock_threshold) 
                             VALUES (%s, %s, %s, %s)""", inv_data)

        print("Loading orders, order_items, shipments, invoices...")
        cur.execute("SELECT product_id, msrp FROM products")
        price_map = dict(cur.fetchall())

        sales_reps = [i for i in range(1, 151) if i % 2 == 0]
        customer_ltv = dict.fromkeys(range(1, 401), 0)

        order_data = []
        item_data = []
        ship_data = []
        inv_docs = []
        item_id_counter = 1

        for o_id in range(1, 3001):
            c_id = random.randint(1, 400)
            s_rep = random.choice(sales_reps)
            date_obj = datetime.now() - timedelta(days=random.randint(1, 700))
            date = date_obj.date()

            status = random.choice(["Completed", "Completed", "Completed", "Processing", "Cancelled"])
            order_total = 0

            for _ in range(random.randint(1, 5)):
                p_id = random.randint(1, 50)
                qty = random.randint(1, 10)
                subtotal = round(price_map[p_id] * qty, 2)
                order_total += subtotal
                item_data.append((o_id, p_id, qty, subtotal))
                item_id_counter += 1

            customer_ltv[c_id] += order_total
            order_data.append((c_id, s_rep, date, round(order_total, 2), status))

            if status != "Cancelled":
                w_id = random.randint(1, 3)
                d_date = (date_obj + timedelta(days=random.randint(1, 3))).date()
                del_date = (date_obj + timedelta(days=random.randint(4, 10))).date() if status == "Completed" else None
                ship_data.append((o_id, w_id, d_date, del_date, "Delivered" if status == "Completed" else "In Transit"))

            due = (date_obj + timedelta(days=30)).date()
            paid = (date_obj + timedelta(days=random.randint(5, 45))).date() if status == "Completed" else None
            inv_docs.append((o_id, date, due, paid, "Paid" if paid else "Pending", round(order_total, 2)))

        execute_batch(cur, """INSERT INTO orders (customer_id, sales_rep_emp_id, date, total_amount, status) 
                             VALUES (%s, %s, %s, %s, %s)""", order_data)
        execute_batch(cur, """INSERT INTO order_items (order_id, product_id, quantity, subtotal) 
                             VALUES (%s, %s, %s, %s)""", item_data)
        execute_batch(cur, """INSERT INTO shipments (order_id, warehouse_id, dispatch_date, delivery_date, status) 
                             VALUES (%s, %s, %s, %s, %s)""", ship_data)
        execute_batch(cur, """INSERT INTO invoices (order_id, issue_date, due_date, paid_date, status, amount) 
                             VALUES (%s, %s, %s, %s, %s, %s)""", inv_docs)

        print("Updating customer LTV...")
        ltv_updates = [(total, c_id) for c_id, total in customer_ltv.items()]
        execute_batch(cur, "UPDATE customers SET total_ltv = %s WHERE customer_id = %s", ltv_updates)

        conn.commit()
        print("Data load complete!")

    except Exception as e:
        conn.rollback()
        print(f"Error: {e}")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    load_data()
