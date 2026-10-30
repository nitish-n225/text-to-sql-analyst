"""
Database seeder for the sample business database.
Populates customers, products, orders, and order_items with realistic synthetic data.
"""

import os
import random
from datetime import datetime, date, timedelta
from typing import Optional
from src.database import DatabaseManager
from src.models import Base, Customer, Product, Order, OrderItem

def seed_sample_database(db_manager: Optional[DatabaseManager] = None, reset: bool = False) -> DatabaseManager:
    """
    Initializes and populates business.db with realistic records.
    """
    db = db_manager or DatabaseManager()
    
    # If database file exists and reset requested, drop all and recreate
    if reset and os.path.exists(db.db_path):
        Base.metadata.drop_all(bind=db.rw_engine)

    db.init_database()

    session = db.get_session()
    try:
        # Check if already seeded
        existing_customers = session.query(Customer).count()
        if existing_customers >= 40 and not reset:
            session.close()
            return db

        # 1. Seed Products (25 items across 5 categories)
        products_data = [
            # Electronics
            ("ProBook Ultra 16-inch", "Electronics", 1399.99, 900.00, 35, 4.8),
            ("Noise-Cancelling Studio Pro", "Electronics", 279.99, 130.00, 110, 4.7),
            ("4K UHD Smart Cinema Monitor 32-inch", "Electronics", 499.99, 310.00, 40, 4.6),
            ("Precision Wireless Ergonomic Mouse", "Electronics", 59.99, 22.00, 240, 4.5),
            ("Mechanical RGB Tactile Keyboard", "Electronics", 129.99, 60.00, 95, 4.6),
            ("Thunderbolt 4 Multi-Port Docking Station", "Electronics", 189.99, 85.00, 75, 4.4),
            # Apparel
            ("Merino Wool Everyday Crewneck", "Apparel", 89.99, 32.00, 120, 4.7),
            ("Waterproof Trail Runner XT", "Apparel", 149.99, 58.00, 65, 4.5),
            ("Classic Stretch Denim Jeans", "Apparel", 74.99, 26.00, 180, 4.3),
            ("Premium Pima Cotton Tee 3-Pack", "Apparel", 39.99, 12.00, 260, 4.6),
            ("Italian Nappa Leather Bomber Jacket", "Apparel", 389.99, 175.00, 30, 4.9),
            # Home & Living
            ("Pour-Over Artisan Coffee Station", "Home & Living", 54.99, 18.00, 140, 4.8),
            ("Ergonomic Mesh Task Office Chair", "Home & Living", 289.99, 120.00, 45, 4.7),
            ("Tri-Ply Stainless Steel 10-Piece Cookware", "Home & Living", 249.99, 105.00, 40, 4.8),
            ("Bamboo Shredded Memory Foam Pillow", "Home & Living", 44.99, 16.00, 190, 4.4),
            ("Minimalist Scandinavian Floor Lamp", "Home & Living", 119.99, 48.00, 80, 4.5),
            # Sports & Fitness
            ("Selectorized Quick-Adjust Dumbbells 50lb", "Sports & Fitness", 349.99, 160.00, 50, 4.8),
            ("High-Density Eco Yoga Mat 6mm", "Sports & Fitness", 42.99, 14.00, 210, 4.6),
            ("Ultra-Lightweight Hydration Vest 12L", "Sports & Fitness", 69.99, 28.00, 90, 4.5),
            ("Solar GPS Adventure Multi-Sport Watch", "Sports & Fitness", 299.99, 145.00, 60, 4.7),
            ("Commercial Grade Resistance Bands Set", "Sports & Fitness", 34.99, 9.50, 300, 4.4),
            # Books & Learning
            ("Designing Data-Intensive Applications", "Books & Media", 54.99, 18.00, 150, 4.9),
            ("Building Machine Learning Powered Applications", "Books & Media", 48.99, 15.00, 130, 4.8),
            ("Staff Engineer: Leadership Beyond the Track", "Books & Media", 32.99, 10.00, 220, 4.7),
            ("Database Systems: The Complete Book", "Books & Media", 69.99, 22.00, 85, 4.6)
        ]

        products = []
        for name, cat, price, cost, stock, rating in products_data:
            p = Product(
                name=name,
                category=cat,
                price=price,
                cost_price=cost,
                stock_quantity=stock,
                rating=rating
            )
            products.append(p)
            session.add(p)

        session.flush() # Populate IDs

        # 2. Seed Customers (50 customers)
        first_names = [
            "Alexander", "Sophia", "Liam", "Emma", "Noah", "Olivia", "James", "Ava", "William", "Isabella",
            "Benjamin", "Mia", "Lucas", "Charlotte", "Henry", "Amelia", "Daniel", "Harper", "Matthew", "Evelyn",
            "Sebastian", "Abigail", "Jack", "Emily", "Samuel", "Elizabeth", "David", "Mila", "Joseph", "Ella"
        ]
        last_names = [
            "Mitchell", "Reynolds", "Chen", "Kowalski", "Vance", "Gupta", "Dubois", "Schmidt", "Tanaka", "Silva",
            "Anderson", "Taylor", "Thomas", "Hernandez", "Moore", "Martin", "Jackson", "Thompson", "White", "Harris",
            "Clark", "Lewis", "Robinson", "Walker", "Perez", "Hall", "Young", "Allen", "Sanchez", "Wright"
        ]
        countries = ["United States", "Canada", "United Kingdom", "Germany", "France", "Japan", "Australia", "Netherlands"]
        loyalty_tiers = ["Bronze", "Silver", "Gold", "Platinum"]

        customers = []
        base_signup = date(2023, 1, 1)

        random.seed(42) # Deterministic realistic seed
        for i in range(50):
            fn = random.choice(first_names)
            ln = random.choice(last_names)
            email = f"{fn.lower()}.{ln.lower()}{i+1}@acme-example.com"
            country = random.choice(countries)
            days_offset = random.randint(0, 600)
            signup = base_signup + timedelta(days=days_offset)
            tier = random.choices(loyalty_tiers, weights=[45, 30, 15, 10])[0]

            c = Customer(
                name=f"{fn} {ln}",
                email=email,
                country=country,
                signup_date=signup,
                loyalty_tier=tier
            )
            customers.append(c)
            session.add(c)

        session.flush()

        # 3. Seed Orders & Order Items (135 orders)
        statuses = ["Delivered", "Delivered", "Delivered", "Shipped", "Processing", "Cancelled", "Refunded"]
        cities = ["New York", "San Francisco", "London", "Berlin", "Tokyo", "Paris", "Sydney", "Toronto", "Austin", "Chicago", "Seattle"]
        payments = ["Credit Card", "Credit Card", "PayPal", "Apple Pay", "Wire Transfer"]

        base_order_date = date(2023, 3, 1)
        total_orders_count = 0

        for cust in customers:
            order_count = random.randint(1, 5)
            for _ in range(order_count):
                order_dt = base_order_date + timedelta(days=random.randint(10, 650))
                status = random.choice(statuses)
                city = random.choice(cities)
                payment = random.choice(payments)

                # Pick 1 to 4 items
                items_in_order = random.randint(1, 4)
                chosen_prods = random.sample(products, items_in_order)

                order = Order(
                    customer_id=cust.id,
                    order_date=order_dt,
                    status=status,
                    total_amount=0.0,
                    shipping_city=city,
                    payment_method=payment
                )
                session.add(order)
                session.flush()

                order_total = 0.0
                for prod in chosen_prods:
                    qty = random.randint(1, 3)
                    disc = random.choice([0.0, 0.05, 0.10, 0.15]) if random.random() > 0.65 else 0.0
                    unit_price = prod.price
                    line_price = round(qty * unit_price * (1.0 - disc), 2)
                    order_total += line_price

                    item = OrderItem(
                        order_id=order.id,
                        product_id=prod.id,
                        quantity=qty,
                        unit_price=unit_price,
                        discount_pct=disc
                    )
                    session.add(item)

                order.total_amount = round(order_total, 2)
                total_orders_count += 1

        session.commit()
        return db
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()

if __name__ == "__main__":
    db = seed_sample_database(reset=True)
    summary = db.get_schema_summary()
    print("Database seeded successfully!")
    for tbl in summary["tables"]:
        print(f"Table: {tbl['table_name']}, Rows: {tbl['row_count']}")
