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
import ctypes
from ctypes import wintypes

class SalesSummary:
    def __init__(self, root, current_user, user_role, db_path):
        self.root = root
        self.root.title("Sales Summary")
        self.root.configure(bg="#F8F9FA")  # Bootstrap light background
        self.root.state('zoomed')  # Maximized window
        self.root.resizable(True, True)
        self.current_user = current_user
        self.user_role = user_role
        self.db_path = db_path
        self.conn = None
        self.main_frame = tk.Frame(self.root, bg="#F8F9FA")
        self.main_frame.pack(fill="both", expand=True)
        self.kpi_labels = {}
        self.display_mode = None
        self.show_sales_summary()
        self.enable_windows_controls()  # Enable Windows control bar

        # Bind keys for window management
        self.root.bind("<F11>", self.toggle_maximize_restore)
        self.root.bind("<Escape>", lambda e: self.root.state('normal'))

    def enable_windows_controls(self):
        hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
        style = ctypes.windll.user32.GetWindowLongW(hwnd, -16)
        style |= 0x00020000  # WS_MINIMIZEBOX
        style |= 0x00010000  # WS_MAXIMIZEBOX
        style |= 0x00080000  # WS_SYSMENU
        ctypes.windll.user32.SetWindowLongW(hwnd, -16, style)
        ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027)

    def get_display_scaling(self) -> float:
        try:
            # Get DPI for the window (96 is standard DPI for 100% scaling)
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            dpi = ctypes.windll.user32.GetDpiForWindow(hwnd)
            scaling_factor = dpi / 96.0  # Convert DPI to scaling factor
            # Round to nearest supported scaling factor (125%, 150%, 175%, 200%)
            supported_scales = [1.25, 1.5, 1.75, 2.0]
            scaling_factor = min(supported_scales, key=lambda x: abs(x - scaling_factor))
            return scaling_factor
        except:
            return 1.75  # Fallback to 175% if detection fails

    def scale_size(self, size: int) -> int:
        scaling_factor = self.get_display_scaling()
        return int(size * scaling_factor)

    def get_writable_db_path(self, db_name="pharmacy.db") -> str:
        app_data = os.getenv('APPDATA', os.path.expanduser("~"))
        db_dir = os.path.join(app_data, "ShinanoPOS")
        os.makedirs(db_dir, exist_ok=True)
        db_path = os.path.join(db_dir, db_name)
        return db_path

    def style_config(self):
        style = ttk.Style()
        style.configure("Treeview", background="#FFFFFF", foreground="#212529",
                        rowheight=self.scale_size(30), font=("Helvetica", self.scale_size(14)))
        style.map("Treeview", background=[("selected", "#007BFF")], foreground=[("selected", "#FFFFFF")])
        style.layout("Treeview", [('Treeview.treearea', {'sticky': 'nswe'})])
        style.configure("Treeview.Heading", font=("Helvetica", self.scale_size(14), "bold"), background="#E9ECEF", foreground="#212529")
        style.configure("grand_total.Treeview", font=("Helvetica", self.scale_size(14), "bold"), background="#E9ECEF")

    def clear_frame(self):
        for widget in self.main_frame.winfo_children():
            widget.destroy()

    def get_user_role(self):
        return self.user_role

    def show_account_management(self):
        self.root.destroy()

    def setup_navigation(self, main_frame):
        nav_frame = tk.Frame(main_frame, bg="#343A40")  # Bootstrap dark navbar
        nav_frame.pack(fill="x")

    def toggle_maximize_restore(self, event=None):
        if self.root.state() == 'zoomed':
            self.root.state('normal')
        else:
            self.root.state('zoomed')

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

        main_frame = tk.Frame(self.main_frame, bg="#F8F9FA")
        main_frame.pack(fill="both", expand=True)

        try:
            self.setup_navigation(main_frame)
        except AttributeError:
            pass

        header = tk.Label(main_frame, text="📊 Sales Summary Dashboard",
                          font=("Helvetica", self.scale_size(26), "bold"),
                          bg="#F8F9FA", fg="#212529")
        header.pack(pady=self.scale_size(20))

        kpi_frame = tk.Frame(main_frame, bg="#F8F9FA")
        kpi_frame.pack(fill="x", padx=self.scale_size(20), pady=self.scale_size(10))

        self.kpi_labels = {}
        for title in ["Today", "This Week", "This Month"]:
            card = tk.Frame(kpi_frame, bg="#FFFFFF", relief="raised", bd=1, highlightbackground="#DEE2E6", highlightthickness=1)
            card.pack(side="left", expand=True, fill="both", padx=self.scale_size(10), pady=self.scale_size(5))
            tk.Label(card, text=title, font=("Helvetica", self.scale_size(16), "bold"),
                     bg="#FFFFFF", fg="#212529").pack(pady=(self.scale_size(10), 0))
            val = tk.Label(card, text="₱ 0.00", font=("Helvetica", self.scale_size(20), "bold"),
                           bg="#FFFFFF", fg="#007BFF")
            val.pack(pady=self.scale_size(10))
            self.kpi_labels[title] = val

        filter_frame = tk.Frame(main_frame, bg="#FFFFFF", relief="raised", bd=1, highlightbackground="#DEE2E6", highlightthickness=1)
        filter_frame.pack(fill="x", padx=self.scale_size(20), pady=self.scale_size(10))

        tk.Label(filter_frame, text="Month:", font=("Helvetica", self.scale_size(16)),
                 bg="#FFFFFF", fg="#212529").pack(side="left", padx=self.scale_size(10))
        month_var = tk.StringVar(value=str(datetime.now().month))
        month_combobox = ttk.Combobox(filter_frame, textvariable=month_var,
                                      values=[str(i) for i in range(1, 13)],
                                      font=("Helvetica", self.scale_size(14)),
                                      width=5, state="readonly")
        month_combobox.pack(side="left", padx=self.scale_size(5))

        tk.Label(filter_frame, text="Year:", font=("Helvetica", self.scale_size(16)),
                 bg="#FFFFFF", fg="#212529").pack(side="left", padx=self.scale_size(10))
        year_var = tk.StringVar(value=str(datetime.now().year))
        year_combobox = ttk.Combobox(filter_frame, textvariable=year_var,
                                     values=[str(i) for i in range(2020, datetime.now().year + 1)],
                                     font=("Helvetica", self.scale_size(14)),
                                     width=7, state="readonly")
        year_combobox.pack(side="left", padx=self.scale_size(5))

        apply_filter_btn = tk.Button(filter_frame, text="🔄 Apply Filter",
                                    command=lambda: self.update_tables_and_kpis(month_var, year_var, monthly_table, daily_table, monthly_frame, daily_frame),
                                    bg="#007BFF", fg="#FFFFFF", font=("Helvetica", self.scale_size(14), "bold"),
                                    activebackground="#0056B3", activeforeground="#FFFFFF",
                                    relief="flat", padx=self.scale_size(12), pady=self.scale_size(6))
        apply_filter_btn.pack(side="left", padx=self.scale_size(10))

        print_report_btn = tk.Button(filter_frame, text="🖨 Print Report",
                                    command=lambda: self.print_sales_report(month_var.get(), year_var.get()),
                                    bg="#28A745", fg="#FFFFFF", font=("Helvetica", self.scale_size(14), "bold"),
                                    activebackground="#218838", activeforeground="#FFFFFF",
                                    relief="flat", padx=self.scale_size(12), pady=self.scale_size(6))
        print_report_btn.pack(side="left", padx=self.scale_size(10))

        self.display_mode = tk.StringVar(value="Daily")
        toggle_btn = tk.Button(filter_frame, text="Show Monthly Sales",
                              command=lambda: self.toggle_sales_view(toggle_btn, monthly_frame, daily_frame, table_container),
                              bg="#FFC107", fg="#212529", font=("Helvetica", self.scale_size(14), "bold"),
                              activebackground="#E0A800", activeforeground="#212529",
                              relief="flat", padx=self.scale_size(12), pady=self.scale_size(6))
        toggle_btn.pack(side="left", padx=self.scale_size(10))

        table_container = tk.Frame(main_frame, bg="#FFFFFF", relief="raised", bd=1, highlightbackground="#DEE2E6", highlightthickness=1)
        table_container.pack(fill="both", expand=True, padx=self.scale_size(20), pady=self.scale_size(20))

        monthly_label = tk.Label(table_container, text="Monthly Sales Summary",
                                font=("Helvetica", self.scale_size(18), "bold"),
                                bg="#FFFFFF", fg="#212529", name="monthly_label")
        monthly_label.pack_forget()

        monthly_frame = tk.Frame(table_container, bg="#FFFFFF", name="monthly_frame")
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
                              bg="#FFFFFF", fg="#212529", name="daily_label")
        daily_label.pack(anchor="w", pady=(self.scale_size(15), self.scale_size(5)))

        daily_frame = tk.Frame(table_container, bg="#FFFFFF", name="daily_frame")
        daily_frame.pack(fill="both", expand=True, pady=self.scale_size(5))

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

        self.style_config()
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

                # Initialize grand totals for monthly table
                grand_total_sales = 0.0
                grand_total_unit_cost = 0.0
                grand_total_net_profit = 0.0

                # Fetch monthly data for the selected month and year
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
                    WHERE strftime('%Y', sale_date) = ? AND strftime('%m', sale_date) = ?
                    GROUP BY strftime('%m', sale_date)
                ''', (year, month.zfill(2)))
                monthly_data = cursor.fetchall()
                print(f"Debug: Monthly data for {year}-{month.zfill(2)}: {monthly_data}")
                month_names = {str(i).zfill(2): name for i, name in enumerate(
                    ["January", "February", "March", "April", "May", "June",
                     "July", "August", "September", "October", "November", "December"], 1)}
                for row in monthly_data:
                    month_num, total_sales, total_unit_cost = row
                    total_sales = total_sales if total_sales is not None else 0
                    total_unit_cost = total_unit_cost if total_unit_cost is not None else 0
                    net_profit = total_sales - total_unit_cost
                    # Accumulate grand totals
                    grand_total_sales += total_sales
                    grand_total_unit_cost += total_unit_cost
                    grand_total_net_profit += net_profit
                    monthly_table.insert("", "end", values=(
                        month_names.get(month_num, month_num),
                        f"₱ {total_sales:.2f}",
                        f"₱ {total_unit_cost:.2f}",
                        f"₱ {net_profit:.2f}"
                    ))

                # Insert grand totals row for monthly table
                if monthly_data:
                    monthly_table.insert("", "end", values=(
                        "GRAND TOTAL",
                        f"₱ {grand_total_sales:.2f}",
                        f"₱ {grand_total_unit_cost:.2f}",
                        f"₱ {grand_total_net_profit:.2f}"
                    ), tags=("grand_total",))
                else:
                    monthly_table.insert("", "end", values=("No data", "₱ 0.00", "₱ 0.00", "₱ 0.00"))

                # Fetch daily data (unchanged)
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
                    total_sales = total_sales if total_sales is not None else 0
                    total_unit_cost = total_unit_cost if total_unit_cost is not None else 0
                    net_profit = total_sales - total_unit_cost
                    daily_table.insert("", "end", values=(
                        sale_date,
                        f"₱ {total_sales:.2f}",
                        f"₱ {total_unit_cost:.2f}",
                        f"₱ {net_profit:.2f}"
                    ))

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
            self.conn = sqlite3.connect(self.db_path)  # Ensure connection is established
            self.update_tables(month_var, year_var, monthly_table, daily_table, monthly_frame, daily_frame)
            self.update_kpis(month_var, year_var)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to update tables and KPIs: {e}", parent=self.root)
        finally:
            if self.conn:
                self.conn.close()
                self.conn = None

    def toggle_sales_view(self, btn, monthly_frame, daily_frame, table_container):
        if self.display_mode.get() == "Daily":
            self.display_mode.set("Monthly")
            btn.config(text="Show Daily Sales", font=("Helvetica", self.scale_size(14), "bold"))
            table_container.children['daily_label'].pack_forget()
            daily_frame.pack_forget()
            table_container.children['monthly_label'].pack(anchor="w", pady=(self.scale_size(15), self.scale_size(5)))
            monthly_frame.pack(fill="both", expand=True, pady=self.scale_size(5))
        else:
            self.display_mode.set("Daily")
            btn.config(text="Show Monthly Sales", font=("Helvetica", self.scale_size(14), "bold"))
            table_container.children['monthly_label'].pack_forget()
            monthly_frame.pack_forget()
            table_container.children['daily_label'].pack(anchor="w", pady=(self.scale_size(15), self.scale_size(5)))
            daily_frame.pack(fill="both", expand=True, pady=self.scale_size(5))

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
            self.conn = sqlite3.connect(self.db_path)
            monthly_sales = {}
            daily_sales = {}

            with self.conn:
                cursor = self.conn.cursor()

                # 🟩 MONTHLY SALES (Jan → selected month)
                cursor.execute("""
                    SELECT 
                        substr(timestamp, 1, 7) AS month,
                        SUM(total_amount) AS total_sales
                    FROM transactions
                    WHERE status = 'Completed'
                    AND (
                            substr(timestamp, 1, 4) = ?
                        OR strftime('%Y', timestamp) = ?
                    )
                    AND CAST(substr(timestamp, 6, 2) AS INTEGER) <= ?
                    GROUP BY substr(timestamp, 1, 7)
                    ORDER BY month ASC
                """, (str(year), str(year), month))
                monthly_data = cursor.fetchall()

                # Convert to dict for easy lookup
                monthly_dict = {m: (s or 0.0) for m, s in monthly_data}

                # Compute per-month unit cost and ensure 0 entries for missing months
                grand_total_sales = grand_total_unit_cost = grand_total_net_profit = 0.0

                for m_num in range(1, month + 1):
                    month_key = f"{year}-{m_num:02d}"
                    total_sales = monthly_dict.get(month_key, 0.0)
                    total_unit_cost = 0.0

                    # Calculate unit cost (if there were transactions)
                    if total_sales > 0:
                        cursor.execute("""
                            SELECT items FROM transactions
                            WHERE status = 'Completed'
                            AND (substr(timestamp, 1, 7) = ? OR strftime('%Y-%m', timestamp) = ?)
                        """, (month_key, month_key))
                        for (items,) in cursor.fetchall():
                            for item_data in items.split(";"):
                                if item_data:
                                    try:
                                        item_id, qty = item_data.split(":")
                                        qty = int(qty)
                                        cursor.execute("SELECT unit_price FROM inventory WHERE item_id = ?", (item_id,))
                                        item = cursor.fetchone()
                                        if item:
                                            total_unit_cost += item[0] * qty
                                    except (ValueError, IndexError):
                                        continue

                    monthly_sales[month_key] = {
                        "grand_sales": total_sales,
                        "unit_sales": total_unit_cost
                    }
                    grand_total_sales += total_sales
                    grand_total_unit_cost += total_unit_cost
                    grand_total_net_profit += (total_sales - total_unit_cost)

                # 🟦 DAILY SALES (only selected month)
                cursor.execute("""
                    SELECT strftime('%Y-%m-%d', timestamp) AS date, items, total_amount
                    FROM transactions
                    WHERE status = 'Completed'
                    AND (timestamp >= ? AND timestamp < ?)
                """, (start_date, end_date))

                total_unit_sales = total_grand_sales = 0.0
                for date, items, total_amount in cursor.fetchall():
                    if date not in daily_sales:
                        daily_sales[date] = {"unit_sales": 0.0, "grand_sales": 0.0}
                    unit_sales = 0.0
                    for item_data in items.split(";"):
                        if item_data:
                            try:
                                item_id, qty = item_data.split(":")
                                qty = int(qty)
                                cursor.execute("SELECT unit_price FROM inventory WHERE item_id = ?", (item_id,))
                                item = cursor.fetchone()
                                if item:
                                    unit_sales += item[0] * qty
                            except (ValueError, IndexError):
                                continue
                    daily_sales[date]["grand_sales"] += total_amount
                    daily_sales[date]["unit_sales"] += unit_sales
                    total_unit_sales += unit_sales
                    total_grand_sales += total_amount

            # 🧾 PDF generation
            receipt_dir = os.path.join(os.path.dirname(self.db_path), "reports")
            os.makedirs(receipt_dir, exist_ok=True)
            report_path = os.path.join(receipt_dir, f"sales_report_{year}_{month:02d}.pdf")

            doc = SimpleDocTemplate(report_path, pagesize=letter)
            styles = getSampleStyleSheet()
            styles['Title'].fontSize = self.scale_size(16)
            styles['Normal'].fontSize = self.scale_size(12)
            styles['Heading2'].fontSize = self.scale_size(14)
            elements = []

            title = Paragraph("<b>Shinano Pharmacy Sales Report</b>", styles['Title'])
            month_name = datetime.strptime(str(month), "%m").strftime("%B")
            period = Paragraph(f"Period: {month_name} {year}", styles['Normal'])
            generated = Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal'])
            elements.extend([title, period, generated, Spacer(1, self.scale_size(12))])

            # ---------------------------
            # MONTHLY SALES SUMMARY
            # ---------------------------
            elements.append(Paragraph("<b>Monthly Sales Summary (Jan - Selected Month)</b>", styles['Heading2']))
            monthly_data_table = [["Month", "Total Sales", "Unit Cost", "Net Profit"]]

            for m_num in range(1, month + 1):
                month_key = f"{year}-{m_num:02d}"
                data = monthly_sales.get(month_key, {"grand_sales": 0.0, "unit_sales": 0.0})
                grand_sales = data["grand_sales"]
                unit_sales = data["unit_sales"]
                net_profit = grand_sales - unit_sales
                month_display = datetime.strptime(month_key, "%Y-%m").strftime("%B")
                monthly_data_table.append([
                    month_display,
                    f"{grand_sales:,.2f}",
                    f"{unit_sales:,.2f}",
                    f"{net_profit:,.2f}"
                ])

            monthly_data_table.append([
                "GRAND TOTAL",
                f"{grand_total_sales:,.2f}",
                f"{grand_total_unit_cost:,.2f}",
                f"{grand_total_net_profit:,.2f}"
            ])

            monthly_table = Table(monthly_data_table, colWidths=[
                self.scale_size(150),
                self.scale_size(100),
                self.scale_size(100),
                self.scale_size(100)
            ])
            monthly_table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#007BFF")),
                ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
                ('ALIGN', (1,1), (-1,-1), 'RIGHT'),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('FONTSIZE', (0,0), (-1,-1), self.scale_size(10)),
                ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0,1), (-1,-1),
                [colors.HexColor("#F8F9FA"), colors.HexColor("#E9ECEF")]),
                ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),
                ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor("#E9ECEF"))
            ]))
            elements.append(monthly_table)
            elements.append(Spacer(1, self.scale_size(24)))

            # ---------------------------
            # DAILY SALES SUMMARY
            # ---------------------------
            elements.append(Paragraph("<b>Daily Sales Summary</b>", styles['Heading2']))
            daily_data_table = [["Date", "Total Sales", "Unit Cost", "Net Profit"]]

            if daily_sales:
                for date in sorted(daily_sales.keys()):
                    grand_sales = daily_sales[date]["grand_sales"]
                    unit_sales = daily_sales[date]["unit_sales"]
                    net_profit = grand_sales - unit_sales
                    daily_data_table.append([
                        date, f"{grand_sales:,.2f}",
                        f"{unit_sales:,.2f}",
                        f"{net_profit:,.2f}"
                    ])
                total_net_profit = total_grand_sales - total_unit_sales
                daily_data_table.append([
                    "TOTAL",
                    f"{total_grand_sales:,.2f}",
                    f"{total_unit_sales:,.2f}",
                    f"{total_net_profit:,.2f}"
                ])
            else:
                daily_data_table.append(["No data available", "-", "-", "-"])

            daily_table = Table(daily_data_table, colWidths=[
                self.scale_size(150),
                self.scale_size(100),
                self.scale_size(100),
                self.scale_size(100)
            ])
            daily_table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#28A745")),
                ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
                ('ALIGN', (1,1), (-1,-1), 'RIGHT'),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('FONTSIZE', (0,0), (-1,-1), self.scale_size(10)),
                ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0,1), (-1,-1),
                [colors.HexColor("#F8F9FA"), colors.HexColor("#E9ECEF")])
            ]))
            elements.append(daily_table)

            doc.build(elements)
            webbrowser.open(f"file://{os.path.abspath(report_path)}")
            messagebox.showinfo("Success", f"Sales report generated at {report_path}", parent=self.root)

        except sqlite3.Error as e:
            messagebox.showerror("Error", f"Database query error: {e}", parent=self.root)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate report: {e}", parent=self.root)
        finally:
            if self.conn:
                self.conn.close()
                self.conn = None


    def __del__(self):
        if hasattr(self, 'conn') and self.conn:
            self.conn.close()