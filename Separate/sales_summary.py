import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
import os
from datetime import datetime, timedelta
from reportlab.platypus import Table, TableStyle, SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
import webbrowser

class SalesSummary:
    def __init__(self, root, current_user, user_role, db_path):
        self.root = root
        self.current_user = current_user
        self.user_role = user_role
        self.db_path = db_path
        self.conn = None
        self.main_frame = tk.Frame(self.root, bg="#F4E1C1")
        self.main_frame.pack(fill="both", expand=True)
        self.kpi_labels = {}
        self.display_mode = None
        self.setup_database()
        self.show_sales_summary()

    def get_writable_db_path(self, db_name="pharmacy.db") -> str:
        app_data = os.getenv('APPDATA', os.path.expanduser("~"))
        db_dir = os.path.join(app_data, "ShinanoPOS")
        os.makedirs(db_dir, exist_ok=True)
        db_path = os.path.join(db_dir, db_name)
        return db_path

    def setup_database(self):
        try:
            self.conn = sqlite3.connect(self.db_path)
            cursor = self.conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS daily_sales (
                    sale_date TEXT PRIMARY KEY,
                    total_sales REAL NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    transaction_id TEXT PRIMARY KEY,
                    items TEXT NOT NULL,
                    total_amount REAL NOT NULL,
                    cash_paid REAL,
                    change_amount REAL,
                    timestamp TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payment_method TEXT,
                    customer_id TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS inventory (
                    item_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    retail_price REAL NOT NULL,
                    unit_price REAL NOT NULL
                )
            """)
            # Insert sample data if tables are empty
            cursor.execute("SELECT COUNT(*) FROM daily_sales")
            if cursor.fetchone()[0] == 0:
                sample_date = datetime.now().strftime("%Y-%m-%d")
                cursor.execute("INSERT INTO daily_sales (sale_date, total_sales) VALUES (?, ?)",
                              (sample_date, 1000.0))
            cursor.execute("SELECT COUNT(*) FROM inventory")
            if cursor.fetchone()[0] == 0:
                cursor.execute("INSERT INTO inventory (item_id, name, quantity, retail_price, unit_price) VALUES (?, ?, ?, ?, ?)",
                              ("item1", "Paracetamol", 100, 10.0, 5.0))
            cursor.execute("SELECT COUNT(*) FROM transactions")
            if cursor.fetchone()[0] == 0:
                cursor.execute("INSERT INTO transactions (transaction_id, items, total_amount, cash_paid, change_amount, timestamp, status, payment_method, customer_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                              ("txn1", "item1:2", 20.0, 50.0, 30.0, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Completed", "Cash", "cust1"))
            self.conn.commit()
        except sqlite3.Error as e:
            messagebox.showerror("Error", f"Failed to set up database: {e}", parent=self.root)
            self.root.destroy()

    def scale_size(self, size: int) -> int:
        base_resolution = 1920
        current_width = self.root.winfo_screenwidth()
        scaling_factor = current_width / base_resolution
        return int(size * scaling_factor)

    def style_config(self):
        style = ttk.Style()
        style.configure("Treeview", background="#FDFEFE", foreground="#2C3E50",
                        rowheight=self.scale_size(26), font=("Helvetica", self.scale_size(12)))
        style.map("Treeview", background=[("selected", "#4DA8DA")])
        style.layout("Treeview", [('Treeview.treearea', {'sticky': 'nswe'})])

    def clear_frame(self):
        for widget in self.main_frame.winfo_children():
            widget.destroy()

    def get_user_role(self):
        return self.user_role

    def show_account_management(self):
        self.root.destroy()

    def setup_navigation(self, main_frame):
        nav_frame = tk.Frame(main_frame, bg="#2C3E50")
        nav_frame.pack(fill="x")
        tk.Button(nav_frame, text="Close", command=self.root.destroy,
                  bg="#E74C3C", fg="white", font=("Helvetica", 14), padx=10, pady=5).pack(side="left", padx=5)

    def show_sales_summary(self) -> None:
        if not hasattr(self, 'root') or self.root is None:
            messagebox.showerror("Error", "Application root is not defined", parent=self.root)
            return
        if self.user_role == "Drug Lord":
            messagebox.showerror("Access Denied", "Admins can only access Account Management.", parent=self.root)
            self.show_account_management()
            return
        elif self.user_role != "Manager":
            messagebox.showerror("Access Denied", "Only Managers can access Sales Summary.", parent=self.root)
            self.root.destroy()
            return
        self.clear_frame()

        main_frame = tk.Frame(self.main_frame, bg="#F4E1C1")
        main_frame.pack(fill="both", expand=True)

        try:
            self.setup_navigation(main_frame)
        except AttributeError:
            pass

        header = tk.Label(main_frame, text="📊 Sales Summary Dashboard",
                          font=("Helvetica", self.scale_size(26), "bold"),
                          bg="#F4E1C1", fg="#2C3E50")
        header.pack(pady=15)

        kpi_frame = tk.Frame(main_frame, bg="#F4E1C1")
        kpi_frame.pack(fill="x", padx=20, pady=10)

        self.kpi_labels = {}
        for title in ["Today", "This Week", "This Month"]:
            card = tk.Frame(kpi_frame, bg="#1B263B", padx=20, pady=20)
            card.pack(side="left", expand=True, fill="both", padx=10)
            tk.Label(card, text=title, font=("Helvetica", 16, "bold"),
                     bg="#1B263B", fg="white").pack()
            val = tk.Label(card, text="₱ 0.00", font=("Helvetica", 20, "bold"),
                           bg="#1B263B", fg="#4DA8DA")
            val.pack()
            self.kpi_labels[title] = val

        filter_frame = tk.Frame(main_frame, bg="#F5F6F5", padx=10, pady=10)
        filter_frame.pack(fill="x", padx=20, pady=10)

        tk.Label(filter_frame, text="Month:", font=("Helvetica", self.scale_size(16)),
                 bg="#F5F6F5", fg="#2C3E50").pack(side="left", padx=5)
        month_var = tk.StringVar(value=str(datetime.now().month))
        month_combobox = ttk.Combobox(filter_frame, textvariable=month_var,
                                      values=[str(i) for i in range(1, 13)],
                                      font=("Helvetica", self.scale_size(14)),
                                      width=5, state="readonly")
        month_combobox.pack(side="left", padx=5)

        tk.Label(filter_frame, text="Year:", font=("Helvetica", self.scale_size(16)),
                 bg="#F5F6F5", fg="#2C3E50").pack(side="left", padx=5)
        year_var = tk.StringVar(value=str(datetime.now().year))
        year_combobox = ttk.Combobox(filter_frame, textvariable=year_var,
                                     values=[str(i) for i in range(2020, datetime.now().year + 1)],
                                     font=("Helvetica", self.scale_size(14)),
                                     width=7, state="readonly")
        year_combobox.pack(side="left", padx=5)

        apply_filter_btn = tk.Button(filter_frame, text="🔄 Apply Filter",
                                    command=lambda: self.update_tables_and_kpis(month_var, year_var, monthly_table, daily_table, monthly_frame, daily_frame),
                                    bg="#4DA8DA", fg="white", font=("Helvetica", 14, "bold"),
                                    padx=12, pady=6, bd=0)
        apply_filter_btn.pack(side="left", padx=10)

        print_report_btn = tk.Button(filter_frame, text="🖨 Print Report",
                                    command=lambda: self.print_sales_report(month_var.get(), year_var.get()),
                                    bg="#2ECC71", fg="white", font=("Helvetica", 14, "bold"),
                                    padx=12, pady=6, bd=0)
        print_report_btn.pack(side="left", padx=10)

        self.display_mode = tk.StringVar(value="Daily")
        toggle_btn = tk.Button(filter_frame, text="Show Monthly Sales",
                              command=lambda: self.toggle_sales_view(toggle_btn, monthly_frame, daily_frame, table_container),
                              bg="#E67E22", fg="white", font=("Helvetica", 14, "bold"),
                              padx=12, pady=6, bd=0)
        toggle_btn.pack(side="left", padx=10)

        table_container = tk.Frame(main_frame, bg="#F5F6F5", padx=20, pady=20)
        table_container.pack(fill="both", expand=True)

        monthly_label = tk.Label(table_container, text="Monthly Sales Summary",
                                font=("Helvetica", self.scale_size(18), "bold"),
                                bg="#F5F6F5", fg="#2C3E50", name="monthly_label")
        monthly_label.pack_forget()

        monthly_frame = tk.Frame(table_container, bg="#F5F6F5", name="monthly_frame")
        monthly_frame.pack_forget()

        columns = ("Month", "TotalSales", "UnitCost", "NetProfit")
        headers = ("MONTH", "TOTAL SALES", "UNIT COST", "NET PROFIT")
        monthly_table = ttk.Treeview(monthly_frame, columns=columns, show="headings", height=8, style="Treeview")
        for col, head in zip(columns, headers):
            monthly_table.heading(col, text=head)
            monthly_table.column(col, width=self.scale_size(150), anchor="center" if col != "Month" else "w")
        monthly_table.pack(fill="both", expand=True)

        daily_label = tk.Label(table_container, text="Daily Sales Summary",
                              font=("Helvetica", self.scale_size(18), "bold"),
                              bg="#F5F6F5", fg="#2C3E50", name="daily_label")
        daily_label.pack(anchor="w", pady=(15, 5))

        daily_frame = tk.Frame(table_container, bg="#F5F6F5", name="daily_frame")
        daily_frame.pack(fill="both", expand=True, pady=5)

        daily_columns = ("Date", "TotalSales", "UnitCost", "NetProfit")
        daily_headers = ("DATE", "TOTAL SALES", "UNIT COST", "NET PROFIT")
        daily_table = ttk.Treeview(daily_frame, columns=daily_columns, show="headings", height=8, style="Treeview")
        for col, head in zip(daily_columns, daily_headers):
            daily_table.heading(col, text=head)
            daily_table.column(col, width=self.scale_size(150), anchor="center" if col != "Date" else "w")
        daily_table.pack(fill="both", expand=True)

        def _on_mouse_wheel(event, treeview):
            if event.delta > 0:
                treeview.yview_scroll(-1, "units")
            else:
                treeview.yview_scroll(1, "units")

        monthly_table.bind("<MouseWheel>", lambda event: _on_mouse_wheel(event, monthly_table))
        daily_table.bind("<MouseWheel>", lambda event: _on_mouse_wheel(event, daily_table))

        self.update_tables_and_kpis(month_var, year_var, monthly_table, daily_table, monthly_frame, daily_frame)

    def update_tables(self, month_var: tk.StringVar, year_var: tk.StringVar, monthly_table: ttk.Treeview, daily_table: ttk.Treeview, monthly_frame: tk.Frame, daily_frame: tk.Frame) -> None:
        for item in monthly_table.get_children():
            monthly_table.delete(item)
        for item in daily_table.get_children():
            daily_table.delete(item)

        try:
            month = month_var.get()
            year = year_var.get()
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("SELECT count(*) FROM daily_sales")
                daily_sales_count = cursor.fetchone()[0]
                cursor.execute("SELECT count(*) FROM transactions")
                transactions_count = cursor.fetchone()[0]
                print(f"Debug: daily_sales rows: {daily_sales_count}, transactions rows: {transactions_count}")

                cursor.execute('''
                    SELECT strftime('%m', sale_date) AS month,
                           SUM(total_sales) AS total_sales,
                           SUM((
                               SELECT SUM(CAST(SUBSTR(t2.items, instr(t2.items, ':') + 1) AS INTEGER) * i.unit_price)
                               FROM transactions t2
                               JOIN inventory i ON instr(t2.items, i.item_id) > 0
                               WHERE strftime('%Y-%m-%d', t2.timestamp) = d.sale_date
                           )) AS total_unit_cost
                    FROM daily_sales d
                    WHERE strftime('%Y', sale_date) = ?
                    GROUP BY strftime('%m', sale_date)
                    ORDER BY month
                ''', (year,))
                monthly_data = cursor.fetchall()
                print(f"Debug: Monthly data for {year}: {monthly_data}")
                month_names = {str(i).zfill(2): name for i, name in enumerate(
                    ["January", "February", "March", "April", "May", "June",
                     "July", "August", "September", "October", "November", "December"], 1)}
                for row in monthly_data:
                    month_num, total_sales, total_unit_cost = row
                    net_profit = (total_sales if total_sales is not None else 0) - (total_unit_cost if total_unit_cost is not None else 0)
                    monthly_table.insert("", "end", values=(
                        month_names.get(month_num, month_num),
                        f"₱ {total_sales if total_sales is not None else 0:.2f}",
                        f"₱ {total_unit_cost if total_unit_cost is not None else 0:.2f}",
                        f"₱ {net_profit:.2f}"
                    ))

                cursor.execute('''
                    SELECT sale_date,
                           total_sales,
                           (
                               SELECT SUM(CAST(SUBSTR(t2.items, instr(t2.items, ':') + 1) AS INTEGER) * i.unit_price)
                               FROM transactions t2
                               JOIN inventory i ON instr(t2.items, i.item_id) > 0
                               WHERE strftime('%Y-%m-%d', t2.timestamp) = d.sale_date
                           ) AS total_unit_cost
                    FROM daily_sales d
                    WHERE strftime('%Y', sale_date) = ? AND strftime('%m', sale_date) = ?
                    ORDER BY sale_date DESC
                ''', (year, month.zfill(2)))
                daily_data = cursor.fetchall()
                print(f"Debug: Daily data for {year}-{month.zfill(2)}: {daily_data}")
                for row in daily_data:
                    sale_date, total_sales, total_unit_cost = row
                    net_profit = (total_sales if total_sales is not None else 0) - (total_unit_cost if total_unit_cost is not None else 0)
                    daily_table.insert("", "end", values=(
                        sale_date,
                        f"₱ {total_sales if total_sales is not None else 0:.2f}",
                        f"₱ {total_unit_cost if total_unit_cost is not None else 0:.2f}",
                        f"₱ {net_profit:.2f}"
                    ))

                if not monthly_data:
                    monthly_table.insert("", "end", values=("No data", "₱ 0.00", "₱ 0.00", "₱ 0.00"))
                if not daily_data:
                    daily_table.insert("", "end", values=("No data", "₱ 0.00", "₱ 0.00", "₱ 0.00"))

        except sqlite3.Error as e:
            print(f"Debug: SQLite error in update_tables: {e}")
            messagebox.showerror("Error", f"Failed to update sales tables: {e}", parent=self.root)

    def update_kpis(self, month_var, year_var):
        try:
            sales_data = {
                "today_sales": 0.0,
                "week_sales": 0.0,
                "month_sales": 0.0
            }
            current_date = datetime.now()
            week_start = current_date - timedelta(days=current_date.weekday())
            month = int(month_var.get())
            year = int(year_var.get())
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute('''
                    SELECT sale_date, total_sales
                    FROM daily_sales
                    WHERE strftime('%Y', sale_date) = ? AND strftime('%m', sale_date) = ?
                ''', (str(year), str(month).zfill(2)))
                daily_data = cursor.fetchall()
                for sale_date, total_sales in daily_data:
                    try:
                        item_date = datetime.strptime(sale_date, "%Y-%m-%d")
                        if item_date.date() == current_date.date():
                            sales_data["today_sales"] += total_sales or 0.0
                        if week_start.date() <= item_date.date() <= current_date.date():
                            sales_data["week_sales"] += total_sales or 0.0
                        if item_date.month == month and item_date.year == year:
                            sales_data["month_sales"] += total_sales or 0.0
                    except ValueError:
                        continue

            self.kpi_labels["Today"].config(text=f"₱ {sales_data['today_sales']:.2f}")
            self.kpi_labels["This Week"].config(text=f"₱ {sales_data['week_sales']:.2f}")
            self.kpi_labels["This Month"].config(text=f"₱ {sales_data['month_sales']:.2f}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to update KPIs: {e}", parent=self.root)

    def update_tables_and_kpis(self, month_var, year_var, monthly_table, daily_table, monthly_frame, daily_frame):
        try:
            self.update_tables(month_var, year_var, monthly_table, daily_table, monthly_frame, daily_frame)
            self.update_kpis(month_var, year_var)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to update tables and KPIs: {e}", parent=self.root)

    def toggle_sales_view(self, btn, monthly_frame, daily_frame, table_container):
        if self.display_mode.get() == "Daily":
            self.display_mode.set("Monthly")
            btn.config(text="Show Daily Sales")
            table_container.children['daily_label'].pack_forget()
            daily_frame.pack_forget()
            table_container.children['monthly_label'].pack(anchor="w", pady=(0, 5))
            monthly_frame.pack(fill="both", expand=True, pady=5)
        else:
            self.display_mode.set("Daily")
            btn.config(text="Show Monthly Sales")
            table_container.children['monthly_label'].pack_forget()
            monthly_frame.pack_forget()
            table_container.children['daily_label'].pack(anchor="w", pady=(15, 5))
            daily_frame.pack(fill="both", expand=True, pady=5)

    def print_sales_report(self, month: str, year: str) -> None:
        try:
            month = int(month)
            year = int(year)
        except ValueError:
            messagebox.showerror("Error", "Invalid month or year selected.", parent=self.root)
            return

        start_date = f"{year}-{month:02d}-01"
        next_month = month + 1 if month < 12 else 1
        next_year = year if month < 12 else year + 1
        end_date = f"{next_year}-{next_month:02d}-01"

        try:
            monthly_sales = {}
            daily_sales = {}
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute("""
                    SELECT strftime('%Y-%m', timestamp) AS month, items, total_amount
                    FROM transactions
                    WHERE status = 'Completed' AND timestamp >= ? AND timestamp < ?
                """, (start_date, end_date))
                for month_str, items, total_amount in cursor.fetchall():
                    if month_str not in monthly_sales:
                        monthly_sales[month_str] = {"unit_sales": 0.0, "grand_sales": 0.0}
                    unit_sales = 0.0
                    for item_data in items.split(";"):
                        if item_data:
                            try:
                                item_id, qty = item_data.split(":")
                                qty = int(qty)
                                cursor.execute("SELECT unit_price FROM inventory WHERE item_id = ?",
                                              (item_id,))
                                item = cursor.fetchone()
                                if item:
                                    unit_sales += item[0] * qty
                            except (ValueError, IndexError):
                                continue
                    monthly_sales[month_str]["unit_sales"] += unit_sales
                    monthly_sales[month_str]["grand_sales"] += total_amount

                cursor.execute("""
                    SELECT strftime('%Y-%m-%d', timestamp) AS date, items, total_amount
                    FROM transactions
                    WHERE status = 'Completed' AND timestamp >= ? AND timestamp < ?
                """, (start_date, end_date))
                total_unit_sales = 0.0
                total_grand_sales = 0.0
                for date, items, total_amount in cursor.fetchall():
                    if date not in daily_sales:
                        daily_sales[date] = {"unit_sales": 0.0, "grand_sales": 0.0}
                    unit_sales = 0.0
                    for item_data in items.split(";"):
                        if item_data:
                            try:
                                item_id, qty = item_data.split(":")
                                qty = int(qty)
                                cursor.execute("SELECT unit_price FROM inventory WHERE item_id = ?",
                                              (item_id,))
                                item = cursor.fetchone()
                                if item:
                                    unit_sales += item[0] * qty
                            except (ValueError, IndexError):
                                continue
                    daily_sales[date]["grand_sales"] += total_amount
                    daily_sales[date]["unit_sales"] += unit_sales
                    total_unit_sales += unit_sales
                    total_grand_sales += total_amount

            receipt_dir = os.path.join(os.path.dirname(self.db_path), "reports")
            os.makedirs(receipt_dir, exist_ok=True)
            report_path = os.path.join(receipt_dir, f"sales_report_{year}_{month:02d}.pdf")

            doc = SimpleDocTemplate(report_path, pagesize=letter)
            styles = getSampleStyleSheet()
            elements = []

            title = Paragraph("<b>Shinano Pharmacy Sales Report</b>", styles['Title'])
            month_name = datetime.strptime(str(month), "%m").strftime("%B")
            period = Paragraph(f"Period: {month_name} {year}", styles['Normal'])
            generated = Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal'])

            elements.extend([title, period, generated, Spacer(1, 12)])

            elements.append(Paragraph("<b>Monthly Sales Summary</b>", styles['Heading2']))
            monthly_data = [["Month", "Total Sales (₱)", "Unit Cost (₱)", "Net Profit (₱)"]]

            if monthly_sales:
                for month_str in sorted(monthly_sales.keys()):
                    grand_sales = monthly_sales[month_str]["grand_sales"]
                    unit_sales = monthly_sales[month_str]["unit_sales"]
                    net_profit = grand_sales - unit_sales
                    month_display = datetime.strptime(month_str, "%Y-%m").strftime("%B %Y")
                    monthly_data.append([month_display, f"{grand_sales:,.2f}", f"{unit_sales:,.2f}", f"{net_profit:,.2f}"])
            else:
                monthly_data.append(["No data available", "-", "-", "-"])

            monthly_table = Table(monthly_data, hAlign="LEFT")
            monthly_table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#003366")),
                ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
                ('ALIGN', (1,1), (-1,-1), 'RIGHT'),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.whitesmoke, colors.lightgrey])
            ]))
            elements.append(monthly_table)
            elements.append(Spacer(1, 24))

            elements.append(Paragraph("<b>Daily Sales Summary</b>", styles['Heading2']))
            daily_data = [["Date", "Total Sales (₱)", "Unit Cost (₱)", "Net Profit (₱)"]]

            if daily_sales:
                for date in sorted(daily_sales.keys()):
                    grand_sales = daily_sales[date]["grand_sales"]
                    unit_sales = daily_sales[date]["unit_sales"]
                    net_profit = grand_sales - unit_sales
                    daily_data.append([date, f"{grand_sales:,.2f}", f"{unit_sales:,.2f}", f"{net_profit:,.2f}"])

                total_net_profit = total_grand_sales - total_unit_sales
                daily_data.append(["TOTAL", f"{total_grand_sales:,.2f}", f"{total_unit_sales:,.2f}", f"{total_net_profit:,.2f}"])
            else:
                daily_data.append(["No data available", "-", "-", "-"])

            daily_table = Table(daily_data, hAlign="LEFT")
            daily_table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#660000")),
                ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
                ('ALIGN', (1,1), (-1,-1), 'RIGHT'),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.whitesmoke, colors.lightgrey])
            ]))
            elements.append(daily_table)

            doc.build(elements)

            try:
                webbrowser.open(f"file://{os.path.abspath(report_path)}")
                messagebox.showinfo("Success", f"Sales report generated at {report_path}", parent=self.root)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to open report: {e}", parent=self.root)

        except sqlite3.Error as e:
            messagebox.showerror("Error", f"Database query error: {e}", parent=self.root)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate report: {e}", parent=self.root)

    def __del__(self):
        if hasattr(self, 'conn') and self.conn:
            self.conn.close()

