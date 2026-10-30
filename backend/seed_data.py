import os
import sqlite3
import random
from datetime import datetime, timedelta

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
os.makedirs(DATA_DIR, exist_ok=True)

def seed_ecommerce():
    db_path = os.path.join(DATA_DIR, "ecommerce.db")
    if os.path.exists(db_path):
        os.remove(db_path)
    
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE,
        country TEXT,
        signup_date DATE,
        loyalty_tier TEXT CHECK(loyalty_tier IN ('Bronze', 'Silver', 'Gold', 'Platinum'))
    )
    """)

    cur.execute("""
    CREATE TABLE categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        description TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        category_id INTEGER REFERENCES categories(id),
        price REAL NOT NULL,
        cost_price REAL NOT NULL,
        stock_quantity INTEGER,
        rating REAL
    )
    """)

    cur.execute("""
    CREATE TABLE orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER REFERENCES customers(id),
        order_date DATE NOT NULL,
        status TEXT CHECK(status IN ('Delivered', 'Shipped', 'Processing', 'Cancelled', 'Refunded')),
        total_amount REAL,
        shipping_city TEXT,
        payment_method TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE order_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER REFERENCES orders(id),
        product_id INTEGER REFERENCES products(id),
        quantity INTEGER NOT NULL,
        unit_price REAL NOT NULL,
        discount_pct REAL DEFAULT 0.0
    )
    """)

    cur.execute("""
    CREATE TABLE reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER REFERENCES products(id),
        customer_id INTEGER REFERENCES customers(id),
        rating INTEGER CHECK(rating BETWEEN 1 AND 5),
        comment TEXT,
        review_date DATE
    )
    """)

    # Populate categories
    categories = [
        ("Electronics", "Gadgets, computing, audio, and smart devices"),
        ("Apparel", "Clothing, shoes, and luxury accessories"),
        ("Home & Living", "Furniture, kitchenware, and decor"),
        ("Fitness & Outdoors", "Workout gear, sports equipment, and apparel"),
        ("Books & Media", "Bestsellers, ebooks, audiobooks, and courses")
    ]
    cur.executemany("INSERT INTO categories (name, description) VALUES (?, ?)", categories)

    # Populate customers
    first_names = ["Alex", "Sophia", "Liam", "Emma", "Noah", "Olivia", "James", "Ava", "William", "Isabella", 
                   "Lucas", "Mia", "Benjamin", "Charlotte", "Elijah", "Amelia", "Daniel", "Harper", "Henry", "Evelyn"]
    last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez",
                  "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin"]
    countries = ["United States", "Canada", "United Kingdom", "Germany", "France", "Japan", "Australia", "India", "Brazil", "Netherlands"]
    tiers = ["Bronze", "Silver", "Gold", "Platinum"]

    customers_data = []
    base_date = datetime(2023, 1, 1)
    for i in range(50):
        fname = random.choice(first_names)
        lname = random.choice(last_names)
        full_name = f"{fname} {lname}"
        email = f"{fname.lower()}.{lname.lower()}{i+1}@example.com"
        country = random.choice(countries)
        signup = (base_date + timedelta(days=random.randint(0, 700))).strftime("%Y-%m-%d")
        tier = random.choices(tiers, weights=[40, 30, 20, 10])[0]
        customers_data.append((full_name, email, country, signup, tier))

    cur.executemany("INSERT INTO customers (name, email, country, signup_date, loyalty_tier) VALUES (?, ?, ?, ?, ?)", customers_data)

    # Populate products
    products_raw = [
        ("UltraBook Pro 15", 1, 1299.99, 850.00, 45, 4.8),
        ("Noise-Cancelling Headphones", 1, 249.99, 110.00, 120, 4.6),
        ("Smart 4K OLED TV 55-inch", 1, 899.99, 580.00, 30, 4.7),
        ("Wireless Ergonomic Mouse", 1, 49.99, 18.00, 250, 4.4),
        ("Mechanical Gaming Keyboard", 1, 119.99, 55.00, 85, 4.5),
        ("USB-C Fast Charger Hub", 1, 39.99, 12.00, 300, 4.3),
        ("Classic Merino Wool Sweater", 2, 89.99, 32.00, 95, 4.6),
        ("Waterproof Trail Running Shoes", 2, 139.99, 52.00, 60, 4.5),
        ("Slim-Fit Denim Jeans", 2, 69.99, 24.00, 140, 4.2),
        ("Organic Cotton T-Shirt 3-Pack", 2, 34.99, 11.00, 220, 4.4),
        ("Italian Leather Jacket", 2, 349.99, 160.00, 25, 4.9),
        ("Modern Velvet Accent Chair", 3, 229.99, 95.00, 40, 4.7),
        ("Ceramic Pour-Over Coffee Maker", 3, 44.99, 14.00, 110, 4.8),
        ("Bamboo Memory Foam Pillow", 3, 39.99, 15.00, 180, 4.3),
        ("Stainless Steel Cookware Set", 3, 199.99, 85.00, 35, 4.6),
        ("Adjustable Dumbbell Set (50 lbs)", 4, 299.99, 140.00, 50, 4.8),
        ("Yoga Mat Extra Thick Eco-Friendly", 4, 39.99, 12.00, 160, 4.5),
        ("Hydration Backpack 20L", 4, 59.99, 22.00, 75, 4.4),
        ("GPS Smart Sports Watch", 4, 189.99, 90.00, 65, 4.6),
        ("Deep Work & Productivity Handbook", 5, 24.99, 6.00, 300, 4.9),
        ("Clean Architecture in Practice", 5, 49.99, 14.00, 140, 4.8),
        ("Data Science from Scratch Guide", 5, 39.99, 10.00, 190, 4.7)
    ]
    cur.executemany("INSERT INTO products (name, category_id, price, cost_price, stock_quantity, rating) VALUES (?, ?, ?, ?, ?, ?)", products_raw)

    # Populate orders & order_items
    statuses = ["Delivered", "Delivered", "Delivered", "Shipped", "Processing", "Cancelled"]
    cities = ["New York", "San Francisco", "London", "Berlin", "Tokyo", "Paris", "Sydney", "Toronto", "Austin", "Chicago"]
    payments = ["Credit Card", "Credit Card", "PayPal", "Apple Pay", "Bank Transfer"]

    order_id = 1
    for cust_id in range(1, 51):
        num_orders = random.randint(1, 5)
        for _ in range(num_orders):
            order_date = (base_date + timedelta(days=random.randint(100, 720))).strftime("%Y-%m-%d")
            status = random.choice(statuses)
            shipping_city = random.choice(cities)
            payment = random.choice(payments)

            # Pick 1 to 4 items
            num_items = random.randint(1, 4)
            chosen_products = random.sample(range(1, len(products_raw) + 1), num_items)
            
            order_total = 0.0
            items_to_insert = []
            for prod_id in chosen_products:
                prod = products_raw[prod_id - 1]
                qty = random.randint(1, 3)
                price = prod[2]
                disc = random.choice([0.0, 0.05, 0.1, 0.15]) if random.random() > 0.6 else 0.0
                line_total = qty * price * (1.0 - disc)
                order_total += line_total
                items_to_insert.append((order_id, prod_id, qty, price, disc))
            
            cur.execute("""
            INSERT INTO orders (customer_id, order_date, status, total_amount, shipping_city, payment_method)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (cust_id, order_date, status, round(order_total, 2), shipping_city, payment))

            for it in items_to_insert:
                cur.execute("INSERT INTO order_items (order_id, product_id, quantity, unit_price, discount_pct) VALUES (?, ?, ?, ?, ?)", it)

            order_id += 1

    # Populate reviews
    review_comments = [
        "Exceeded all my expectations! Superior build quality.",
        "Very solid product. Quick shipping and easy setup.",
        "Good value for money, but could have slightly better battery life.",
        "Loved it! Best purchase I made this year.",
        "Decent quality, arrived on time.",
        "Outstanding performance, will recommend to my colleagues.",
        "Works fine, matched the description accurately."
    ]
    for _ in range(40):
        pid = random.randint(1, len(products_raw))
        cid = random.randint(1, 50)
        rt = random.randint(3, 5)
        comm = random.choice(review_comments)
        rdate = (base_date + timedelta(days=random.randint(200, 720))).strftime("%Y-%m-%d")
        cur.execute("INSERT INTO reviews (product_id, customer_id, rating, comment, review_date) VALUES (?, ?, ?, ?, ?)", (pid, cid, rt, comm, rdate))

    conn.commit()
    conn.close()
    print(f"Seeded ecommerce.db successfully ({order_id-1} orders).")

def seed_company_hr():
    db_path = os.path.join(DATA_DIR, "company_hr.db")
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE departments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        budget REAL NOT NULL,
        location TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE employees (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        department_id INTEGER REFERENCES departments(id),
        job_title TEXT NOT NULL,
        salary REAL NOT NULL,
        hire_date DATE NOT NULL,
        performance_rating REAL CHECK(performance_rating BETWEEN 1.0 AND 5.0),
        remote_status TEXT CHECK(remote_status IN ('Remote', 'Hybrid', 'On-Site'))
    )
    """)

    cur.execute("""
    CREATE TABLE projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        department_id INTEGER REFERENCES departments(id),
        budget REAL,
        status TEXT CHECK(status IN ('Planning', 'Active', 'Completed', 'On Hold')),
        start_date DATE,
        end_date DATE
    )
    """)

    cur.execute("""
    CREATE TABLE employee_projects (
        employee_id INTEGER REFERENCES employees(id),
        project_id INTEGER REFERENCES projects(id),
        hours_allocated INTEGER,
        role TEXT,
        PRIMARY KEY (employee_id, project_id)
    )
    """)

    # Departments
    depts = [
        ("Engineering", 1500000.0, "San Francisco"),
        ("Product Management", 650000.0, "New York"),
        ("Data Science & AI", 950000.0, "Seattle"),
        ("Marketing & Growth", 500000.0, "Austin"),
        ("People & Talent", 300000.0, "Chicago"),
        ("Finance & Legal", 450000.0, "Boston")
    ]
    cur.executemany("INSERT INTO departments (name, budget, location) VALUES (?, ?, ?)", depts)

    # Employees
    emp_names = [
        ("Marcus Vance", 1, "Principal Engineer", 185000, "2020-03-15", 4.9, "Remote"),
        ("Elena Rostova", 1, "Senior Backend Engineer", 155000, "2021-06-01", 4.7, "Hybrid"),
        ("David Chen", 1, "Staff Frontend Engineer", 162000, "2020-09-12", 4.8, "Remote"),
        ("Sarah Jenkins", 1, "Cloud DevOps Architect", 170000, "2019-11-04", 4.6, "Hybrid"),
        ("Tariq Al-Mansoor", 1, "Software Engineer II", 125000, "2022-04-18", 4.3, "On-Site"),
        ("Maya Lin", 1, "Junior Software Engineer", 95000, "2023-08-01", 4.1, "On-Site"),
        ("Priya Sharma", 2, "VP of Product", 210000, "2019-02-10", 4.9, "Hybrid"),
        ("Lucas Moreno", 2, "Senior Product Manager", 148000, "2021-01-15", 4.5, "Remote"),
        ("Chloe Bennett", 2, "Associate PM", 102000, "2023-03-20", 4.2, "On-Site"),
        ("Dr. Aris Thorne", 3, "Head of AI Research", 225000, "2020-01-05", 5.0, "Remote"),
        ("Hana Tanaka", 3, "Senior Machine Learning Engineer", 168000, "2021-07-15", 4.8, "Remote"),
        ("Jordan Rivera", 3, "Data Analyst Lead", 132000, "2021-10-01", 4.4, "Hybrid"),
        ("Zoe Campbell", 3, "Data Engineer", 128000, "2022-09-10", 4.3, "Hybrid"),
        ("Oliver Queen", 4, "Marketing Director", 160000, "2020-05-11", 4.6, "On-Site"),
        ("Rachel Green", 4, "Content Strategist", 88000, "2022-02-14", 4.2, "Remote"),
        ("Carlos Santos", 4, "Growth Hacker", 105000, "2022-11-01", 4.4, "Hybrid"),
        ("Amina Diallo", 5, "HR Business Partner", 112000, "2021-04-19", 4.5, "On-Site"),
        ("Samuel Cohen", 5, "Technical Recruiter", 92000, "2022-06-25", 4.3, "Remote"),
        ("Grace Hopper", 6, "Chief Financial Officer", 240000, "2018-08-01", 4.9, "Hybrid"),
        ("Kavita Rao", 6, "Senior Financial Analyst", 118000, "2021-12-05", 4.5, "On-Site")
    ]
    cur.executemany("INSERT INTO employees (name, department_id, job_title, salary, hire_date, performance_rating, remote_status) VALUES (?, ?, ?, ?, ?, ?, ?)", emp_names)

    # Projects
    projects = [
        ("Autonomous Agent Platform", 1, 450000.0, "Active", "2023-01-10", "2024-12-31"),
        ("Core Cloud Migration (Kubernetes)", 1, 320000.0, "Completed", "2022-03-01", "2023-05-15"),
        ("Real-Time Analytics Pipeline", 3, 280000.0, "Active", "2023-04-01", "2024-06-30"),
        ("LLM Fine-Tuning & Evaluation Suite", 3, 350000.0, "Active", "2023-08-15", "2024-08-15"),
        ("Q3 Global Growth Campaign", 4, 180000.0, "Completed", "2023-06-01", "2023-09-30"),
        ("Enterprise SOC2 Compliance Audit", 6, 95000.0, "Completed", "2023-02-01", "2023-06-01")
    ]
    cur.executemany("INSERT INTO projects (title, department_id, budget, status, start_date, end_date) VALUES (?, ?, ?, ?, ?, ?)", projects)

    # Allocations
    allocs = [
        (1, 1, 30, "Tech Lead"),
        (2, 1, 40, "Core Developer"),
        (3, 1, 35, "Frontend Specialist"),
        (4, 2, 40, "Infrastructure Lead"),
        (10, 4, 25, "AI Principal"),
        (11, 4, 35, "ML Lead"),
        (12, 3, 30, "Analytics Architect"),
        (13, 3, 40, "Pipeline Engineer"),
        (7, 1, 15, "Product Owner"),
        (8, 4, 20, "Product Manager"),
        (14, 5, 25, "Campaign Lead")
    ]
    cur.executemany("INSERT INTO employee_projects (employee_id, project_id, hours_allocated, role) VALUES (?, ?, ?, ?)", allocs)

    conn.commit()
    conn.close()
    print("Seeded company_hr.db successfully.")

def seed_healthcare():
    db_path = os.path.join(DATA_DIR, "healthcare.db")
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE patients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        age INTEGER NOT NULL,
        gender TEXT CHECK(gender IN ('M', 'F', 'Other')),
        blood_type TEXT,
        insurance_provider TEXT,
        city TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE doctors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        specialty TEXT NOT NULL,
        years_experience INTEGER,
        consultation_fee REAL
    )
    """)

    cur.execute("""
    CREATE TABLE appointments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER REFERENCES patients(id),
        doctor_id INTEGER REFERENCES doctors(id),
        appointment_date DATE NOT NULL,
        status TEXT CHECK(status IN ('Completed', 'Scheduled', 'Cancelled', 'No-Show')),
        diagnosis TEXT,
        billing_amount REAL
    )
    """)

    doctors_data = [
        ("Dr. Gregory House", "Diagnostic Medicine", 22, 350.0),
        ("Dr. Allison Cameron", "Immunology", 12, 220.0),
        ("Dr. Robert Chase", "Intensive Care & Surgery", 14, 280.0),
        ("Dr. Eric Foreman", "Neurology", 15, 260.0),
        ("Dr. Lisa Cuddy", "Endocrinology", 20, 310.0),
        ("Dr. James Wilson", "Oncology", 18, 300.0)
    ]
    cur.executemany("INSERT INTO doctors (name, specialty, years_experience, consultation_fee) VALUES (?, ?, ?, ?)", doctors_data)

    patients_sample = [
        ("Arthur Morgan", 38, "M", "O+", "Blue Cross", "Boston"),
        ("Sadie Adler", 29, "F", "A+", "Aetna", "Chicago"),
        ("John Marston", 35, "M", "B-", "UnitedHealth", "Denver"),
        ("Abigail Roberts", 32, "F", "AB+", "Kaiser", "Seattle"),
        ("Charles Smith", 27, "M", "O-", "Cigna", "Portland"),
        ("Mary Beth", 24, "F", "A-", "Aetna", "Boston"),
        ("Josiah Trelawny", 52, "M", "B+", "Blue Cross", "New York"),
        ("Susan Grimshaw", 58, "F", "O+", "Medicare", "Philadelphia"),
        ("Micah Bell", 43, "M", "AB-", "None", "Dallas"),
        ("Dutch van der Linde", 49, "M", "A+", "UnitedHealth", "Austin"),
        ("Hosea Matthews", 64, "M", "O+", "Medicare", "San Diego"),
        ("Tilly Jackson", 22, "F", "B+", "Blue Cross", "Atlanta"),
        ("Karen Jones", 26, "F", "O-", "Cigna", "Miami"),
        ("Javier Escuella", 31, "M", "A-", "Kaiser", "Phoenix"),
        ("Bill Williamson", 40, "M", "B-", "Aetna", "San Antonio")
    ]
    cur.executemany("INSERT INTO patients (name, age, gender, blood_type, insurance_provider, city) VALUES (?, ?, ?, ?, ?, ?)", patients_sample)

    diagnoses = [
        ("Hypertension", 450.0), ("Type 2 Diabetes", 600.0), ("Migraine with Aura", 320.0),
        ("Acute Bronchitis", 280.0), ("Vitamin D Deficiency", 150.0), ("Rheumatoid Arthritis", 850.0),
        ("Seasonal Allergies", 120.0), ("Carpal Tunnel Syndrome", 500.0), ("General Health Checkup", 200.0)
    ]

    base = datetime(2023, 1, 1)
    for i in range(40):
        pat_id = random.randint(1, len(patients_sample))
        doc_id = random.randint(1, len(doctors_data))
        adate = (base + timedelta(days=random.randint(10, 700))).strftime("%Y-%m-%d")
        status = random.choice(["Completed", "Completed", "Completed", "Scheduled", "Cancelled"])
        diag, bill = random.choice(diagnoses)
        cur.execute("INSERT INTO appointments (patient_id, doctor_id, appointment_date, status, diagnosis, billing_amount) VALUES (?, ?, ?, ?, ?, ?)",
                    (pat_id, doc_id, adate, status, diag, bill))

    conn.commit()
    conn.close()
    print("Seeded healthcare.db successfully.")

if __name__ == "__main__":
    seed_ecommerce()
    seed_company_hr()
    seed_healthcare()
    print("All sample databases created successfully!")
