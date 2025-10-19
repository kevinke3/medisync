from flask import Flask, render_template, request, jsonify, flash, redirect, url_for, send_file
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models import db, User, Medicine, Supplier, Sale, SaleItem, Prescription
from config import Config
from datetime import datetime, timedelta
import json
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
import qrcode

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Authentication Routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password) and user.is_active:
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        else:
            flash('Invalid username or password', 'danger')
    
    return render_template('auth/login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# Dashboard
@app.route('/')
@login_required
def dashboard():
    # Dashboard statistics
    total_medicines = Medicine.query.count()
    low_stock_medicines = Medicine.query.filter(Medicine.quantity <= Medicine.min_stock_level).count()
    total_sales_today = Sale.query.filter(
        db.func.date(Sale.created_at) == datetime.today().date()
    ).count()
    total_revenue_today = db.session.query(
        db.func.sum(Sale.final_amount)
    ).filter(db.func.date(Sale.created_at) == datetime.today().date()).scalar() or 0
    
    # Expiring medicines (within 30 days)
    expiring_medicines = Medicine.query.filter(
        Medicine.expiry_date <= datetime.today().date() + timedelta(days=30)
    ).order_by(Medicine.expiry_date).limit(5).all()
    
    return render_template('dashboard.html',
                         total_medicines=total_medicines,
                         low_stock_medicines=low_stock_medicines,
                         total_sales_today=total_sales_today,
                         total_revenue_today=total_revenue_today,
                         expiring_medicines=expiring_medicines)

# Medicine Management
@app.route('/medicines')
@login_required
def medicines():
    if current_user.role not in ['admin', 'pharmacist']:
        flash('Access denied', 'danger')
        return redirect(url_for('dashboard'))
    
    medicines_list = Medicine.query.all()
    return render_template('medicines/index.html', medicines=medicines_list)

@app.route('/medicines/add', methods=['GET', 'POST'])
@login_required
def add_medicine():
    if current_user.role not in ['admin', 'pharmacist']:
        flash('Access denied', 'danger')
        return redirect(url_for('medicines'))
    
    suppliers = Supplier.query.all()
    if request.method == 'POST':
        try:
            medicine = Medicine(
                name=request.form['name'],
                generic_name=request.form.get('generic_name'),
                category=request.form.get('category'),
                batch_number=request.form['batch_number'],
                quantity=int(request.form['quantity']),
                price=float(request.form['price']),
                cost_price=float(request.form.get('cost_price', 0)),
                expiry_date=datetime.strptime(request.form['expiry_date'], '%Y-%m-%d').date(),
                supplier_id=request.form.get('supplier_id') or None,
                min_stock_level=int(request.form.get('min_stock_level', 10)),
                is_prescription_required=bool(request.form.get('is_prescription_required'))
            )
            db.session.add(medicine)
            db.session.commit()
            flash('Medicine added successfully', 'success')
            return redirect(url_for('medicines'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding medicine: {str(e)}', 'danger')
    
    return render_template('medicines/add.html', suppliers=suppliers)

@app.route('/medicines/<int:medicine_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_medicine(medicine_id):
    if current_user.role not in ['admin', 'pharmacist']:
        flash('Access denied', 'danger')
        return redirect(url_for('medicines'))
    
    medicine = Medicine.query.get_or_404(medicine_id)
    suppliers = Supplier.query.all()
    
    if request.method == 'POST':
        try:
            medicine.name = request.form['name']
            medicine.generic_name = request.form.get('generic_name')
            medicine.category = request.form.get('category')
            medicine.batch_number = request.form['batch_number']
            medicine.quantity = int(request.form['quantity'])
            medicine.price = float(request.form['price'])
            medicine.cost_price = float(request.form.get('cost_price', 0))
            medicine.expiry_date = datetime.strptime(request.form['expiry_date'], '%Y-%m-%d').date()
            medicine.supplier_id = request.form.get('supplier_id') or None
            medicine.min_stock_level = int(request.form.get('min_stock_level', 10))
            medicine.is_prescription_required = bool(request.form.get('is_prescription_required'))
            
            db.session.commit()
            flash('Medicine updated successfully', 'success')
            return redirect(url_for('medicines'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating medicine: {str(e)}', 'danger')
    
    return render_template('medicines/edit.html', medicine=medicine, suppliers=suppliers)

@app.route('/medicines/<int:medicine_id>/delete', methods=['POST'])
@login_required
def delete_medicine(medicine_id):
    if current_user.role not in ['admin', 'pharmacist']:
        flash('Access denied', 'danger')
        return redirect(url_for('medicines'))
    
    medicine = Medicine.query.get_or_404(medicine_id)
    try:
        db.session.delete(medicine)
        db.session.commit()
        flash('Medicine deleted successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting medicine: {str(e)}', 'danger')
    
    return redirect(url_for('medicines'))

# Supplier Management
@app.route('/suppliers')
@login_required
def suppliers():
    if current_user.role != 'admin':
        flash('Access denied', 'danger')
        return redirect(url_for('dashboard'))
    
    suppliers_list = Supplier.query.all()
    return render_template('suppliers/index.html', suppliers=suppliers_list)

@app.route('/suppliers/add', methods=['GET', 'POST'])
@login_required
def add_supplier():
    if current_user.role != 'admin':
        flash('Access denied', 'danger')
        return redirect(url_for('suppliers'))
    
    if request.method == 'POST':
        try:
            supplier = Supplier(
                name=request.form['name'],
                contact_person=request.form.get('contact_person'),
                email=request.form.get('email'),
                phone=request.form.get('phone'),
                address=request.form.get('address'),
                tax_id=request.form.get('tax_id'),
                payment_terms=request.form.get('payment_terms')
            )
            db.session.add(supplier)
            db.session.commit()
            flash('Supplier added successfully', 'success')
            return redirect(url_for('suppliers'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding supplier: {str(e)}', 'danger')
    
    return render_template('suppliers/add.html')

# Sales Management
@app.route('/sales')
@login_required
def sales():
    sales_list = Sale.query.order_by(Sale.created_at.desc()).all()
    return render_template('sales/index.html', sales=sales_list)

@app.route('/sales/new', methods=['GET', 'POST'])
@login_required
def new_sale():
    if request.method == 'POST':
        try:
            sale_data = request.get_json()
            invoice_number = f"INV-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            
            sale = Sale(
                invoice_number=invoice_number,
                customer_name=sale_data.get('customer_name', 'Walk-in Customer'),
                customer_phone=sale_data.get('customer_phone', ''),
                total_amount=float(sale_data['total_amount']),
                discount=float(sale_data.get('discount', 0)),
                tax_amount=float(sale_data.get('tax_amount', 0)),
                final_amount=float(sale_data['final_amount']),
                payment_method=sale_data.get('payment_method', 'cash'),
                cashier_id=current_user.id
            )
            
            db.session.add(sale)
            db.session.flush()  # Get sale ID
            
            for item in sale_data['items']:
                medicine = Medicine.query.get(item['medicine_id'])
                if medicine.quantity < item['quantity']:
                    return jsonify({'success': False, 'message': f'Insufficient stock for {medicine.name}'})
                
                sale_item = SaleItem(
                    sale_id=sale.id,
                    medicine_id=item['medicine_id'],
                    quantity=item['quantity'],
                    unit_price=item['unit_price'],
                    total_price=item['total_price']
                )
                db.session.add(sale_item)
                
                # Update stock
                medicine.quantity -= item['quantity']
            
            db.session.commit()
            return jsonify({'success': True, 'invoice_number': invoice_number, 'sale_id': sale.id})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': str(e)})
    
    medicines_list = Medicine.query.filter(Medicine.quantity > 0).all()
    return render_template('sales/new.html', medicines=medicines_list)

@app.route('/sales/<int:sale_id>')
@login_required
def sale_detail(sale_id):
    sale = Sale.query.get_or_404(sale_id)
    return render_template('sales/detail.html', sale=sale)

# Prescription Management
@app.route('/prescriptions')
@login_required
def prescriptions():
    if current_user.role not in ['admin', 'pharmacist']:
        flash('Access denied', 'danger')
        return redirect(url_for('dashboard'))
    
    prescriptions_list = Prescription.query.order_by(Prescription.created_at.desc()).all()
    return render_template('prescriptions/index.html', prescriptions=prescriptions_list)

@app.route('/prescriptions/add', methods=['GET', 'POST'])
@login_required
def add_prescription():
    if current_user.role not in ['admin', 'pharmacist']:
        flash('Access denied', 'danger')
        return redirect(url_for('prescriptions'))
    
    if request.method == 'POST':
        try:
            prescription = Prescription(
                patient_name=request.form['patient_name'],
                patient_age=int(request.form.get('patient_age', 0)),
                patient_gender=request.form.get('patient_gender'),
                doctor_name=request.form['doctor_name'],
                doctor_license=request.form.get('doctor_license'),
                diagnosis=request.form.get('diagnosis'),
                prescribed_medicines=request.form.get('prescribed_medicines'),
                date_issued=datetime.strptime(request.form['date_issued'], '%Y-%m-%d').date()
            )
            db.session.add(prescription)
            db.session.commit()
            flash('Prescription added successfully', 'success')
            return redirect(url_for('prescriptions'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding prescription: {str(e)}', 'danger')
    
    return render_template('prescriptions/add.html')

@app.route('/prescriptions/<int:prescription_id>/fulfill', methods=['POST'])
@login_required
def fulfill_prescription(prescription_id):
    if current_user.role not in ['admin', 'pharmacist']:
        flash('Access denied', 'danger')
        return redirect(url_for('prescriptions'))
    
    prescription = Prescription.query.get_or_404(prescription_id)
    try:
        prescription.is_fulfilled = True
        db.session.commit()
        flash('Prescription marked as fulfilled', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error fulfilling prescription: {str(e)}', 'danger')
    
    return redirect(url_for('prescriptions'))

# Analytics API
@app.route('/api/analytics/daily-revenue')
@login_required
def daily_revenue_analytics():
    if current_user.role != 'admin':
        return jsonify({'error': 'Access denied'}), 403
    
    # Last 7 days revenue data
    dates = []
    revenues = []
    for i in range(6, -1, -1):
        date = datetime.today().date() - timedelta(days=i)
        revenue = db.session.query(db.func.sum(Sale.final_amount)).filter(
            db.func.date(Sale.created_at) == date
        ).scalar() or 0
        
        dates.append(date.strftime('%m-%d'))
        revenues.append(float(revenue))
    
    return jsonify({'dates': dates, 'revenues': revenues})

@app.route('/api/analytics/top-medicines')
@login_required
def top_medicines_analytics():
    if current_user.role != 'admin':
        return jsonify({'error': 'Access denied'}), 403
    
    # Top 10 selling medicines
    top_medicines = db.session.query(
        Medicine.name,
        db.func.sum(SaleItem.quantity).label('total_sold')
    ).join(SaleItem).group_by(Medicine.id).order_by(
        db.func.sum(SaleItem.quantity).desc()
    ).limit(10).all()
    
    labels = [med[0] for med in top_medicines]
    data = [int(med[1]) for med in top_medicines]
    
    return jsonify({'labels': labels, 'data': data})

# PDF Invoice Generation
@app.route('/sales/<int:sale_id>/invoice')
@login_required
def generate_invoice(sale_id):
    sale = Sale.query.get_or_404(sale_id)
    
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    
    # Add invoice content
    p.drawString(100, 750, f"Invoice: {sale.invoice_number}")
    p.drawString(100, 730, f"Date: {sale.created_at.strftime('%Y-%m-%d %H:%M')}")
    p.drawString(100, 710, f"Customer: {sale.customer_name}")
    
    y_position = 680
    for item in sale.items:
        p.drawString(100, y_position, f"{item.medicine.name} - {item.quantity} x ${item.unit_price}")
        y_position -= 20
    
    p.drawString(100, y_position - 40, f"Total Amount: ${sale.final_amount}")
    
    p.showPage()
    p.save()
    
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f"invoice_{sale.invoice_number}.pdf", mimetype='application/pdf')

# Analytics Routes
@app.route('/analytics')
@login_required
def analytics():
    if not current_user.can_access_module('analytics'):
        flash('Access denied', 'danger')
        return redirect(url_for('dashboard'))
    
    return render_template('analytics/index.html')

@app.route('/api/analytics/sales-data')
@login_required
def sales_analytics_data():
    if not current_user.can_access_module('analytics'):
        return jsonify({'error': 'Access denied'}), 403
    
    # Sales data for the last 30 days
    dates = []
    sales_count = []
    revenue_data = []
    
    for i in range(29, -1, -1):
        date = datetime.today().date() - timedelta(days=i)
        daily_sales = Sale.query.filter(db.func.date(Sale.created_at) == date).all()
        
        dates.append(date.strftime('%m-%d'))
        sales_count.append(len(daily_sales))
        revenue_data.append(float(sum(sale.final_amount for sale in daily_sales)))
    
    return jsonify({
        'dates': dates,
        'sales_count': sales_count,
        'revenue': revenue_data
    })

@app.route('/api/analytics/stock-data')
@login_required
def stock_analytics_data():
    if not current_user.can_access_module('analytics'):
        return jsonify({'error': 'Access denied'}), 403
    
    # Stock analytics
    total_medicines = Medicine.query.count()
    low_stock = Medicine.query.filter(Medicine.quantity <= Medicine.min_stock_level).count()
    out_of_stock = Medicine.query.filter(Medicine.quantity == 0).count()
    expiring_soon = Medicine.query.filter(
        Medicine.expiry_date <= datetime.today().date() + timedelta(days=30)
    ).count()
    
    return jsonify({
        'total_medicines': total_medicines,
        'low_stock': low_stock,
        'out_of_stock': out_of_stock,
        'expiring_soon': expiring_soon
    })

@app.route('/api/analytics/category-data')
@login_required
def category_analytics_data():
    if not current_user.can_access_module('analytics'):
        return jsonify({'error': 'Access denied'}), 403
    
    # Medicine categories distribution
    categories = db.session.query(
        Medicine.category,
        db.func.count(Medicine.id).label('count')
    ).filter(Medicine.category.isnot(None)).group_by(Medicine.category).all()
    
    category_labels = [cat[0] for cat in categories]
    category_data = [cat[1] for cat in categories]
    
    return jsonify({
        'labels': category_labels,
        'data': category_data
    })

# Reports Routes
@app.route('/reports')
@login_required
def reports():
    if not current_user.can_access_module('reports'):
        flash('Access denied', 'danger')
        return redirect(url_for('dashboard'))
    
    return render_template('reports/index.html')

@app.route('/api/reports/sales-report')
@login_required
def sales_report():
    if not current_user.can_access_module('reports'):
        return jsonify({'error': 'Access denied'}), 403
    
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    query = Sale.query
    
    if start_date:
        query = query.filter(Sale.created_at >= datetime.strptime(start_date, '%Y-%m-%d'))
    if end_date:
        query = query.filter(Sale.created_at <= datetime.strptime(end_date + ' 23:59:59', '%Y-%m-%d %H:%M:%S'))
    
    sales = query.order_by(Sale.created_at.desc()).all()
    
    report_data = []
    for sale in sales:
        report_data.append({
            'invoice_number': sale.invoice_number,
            'date': sale.created_at.strftime('%Y-%m-%d %H:%M'),
            'customer': sale.customer_name,
            'items': len(sale.items),
            'total_amount': float(sale.final_amount),
            'payment_method': sale.payment_method
        })
    
    return jsonify(report_data)

@app.route('/api/reports/stock-report')
@login_required
def stock_report():
    if not current_user.can_access_module('reports'):
        return jsonify({'error': 'Access denied'}), 403
    
    medicines = Medicine.query.order_by(Medicine.quantity.asc()).all()
    
    report_data = []
    for medicine in medicines:
        report_data.append({
            'name': medicine.name,
            'generic_name': medicine.generic_name,
            'batch_number': medicine.batch_number,
            'quantity': medicine.quantity,
            'min_stock_level': medicine.min_stock_level,
            'price': float(medicine.price),
            'expiry_date': medicine.expiry_date.strftime('%Y-%m-%d'),
            'status': 'Out of Stock' if medicine.quantity == 0 else 
                     'Low Stock' if medicine.quantity <= medicine.min_stock_level else 
                     'In Stock'
        })
    
    return jsonify(report_data)

@app.route('/api/reports/export-sales')
@login_required
def export_sales_report():
    if not current_user.can_access_module('reports'):
        return jsonify({'error': 'Access denied'}), 403
    
    # Generate CSV report
    import csv
    from io import StringIO
    
    sales = Sale.query.order_by(Sale.created_at.desc()).all()
    
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Invoice', 'Date', 'Customer', 'Items', 'Total Amount', 'Payment Method'])
    
    for sale in sales:
        writer.writerow([
            sale.invoice_number,
            sale.created_at.strftime('%Y-%m-%d %H:%M'),
            sale.customer_name,
            len(sale.items),
            sale.final_amount,
            sale.payment_method
        ])
    
    output.seek(0)
    return send_file(
        StringIO(output.getvalue()),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'sales_report_{datetime.now().strftime("%Y%m%d")}.csv'
    )

# Settings and User Management Routes
@app.route('/settings')
@login_required
def settings():
    if not current_user.can_access_module('settings'):
        flash('Access denied', 'danger')
        return redirect(url_for('dashboard'))
    
    users = User.query.all()
    return render_template('settings/index.html', users=users)

@app.route('/settings/users/add', methods=['POST'])
@login_required
def add_user():
    if current_user.role != 'admin':
        flash('Access denied', 'danger')
        return redirect(url_for('settings'))
    
    try:
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'danger')
            return redirect(url_for('settings'))
        
        if User.query.filter_by(email=email).first():
            flash('Email already exists', 'danger')
            return redirect(url_for('settings'))
        
        user = User(username=username, email=email, role=role)
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        flash('User created successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error creating user: {str(e)}', 'danger')
    
    return redirect(url_for('settings'))

@app.route('/settings/users/<int:user_id>/toggle', methods=['POST'])
@login_required
def toggle_user(user_id):
    if current_user.role != 'admin':
        flash('Access denied', 'danger')
        return redirect(url_for('settings'))
    
    if user_id == current_user.id:
        flash('Cannot deactivate your own account', 'warning')
        return redirect(url_for('settings'))
    
    user = User.query.get_or_404(user_id)
    try:
        user.is_active = not user.is_active
        db.session.commit()
        
        status = 'activated' if user.is_active else 'deactivated'
        flash(f'User {status} successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating user: {str(e)}', 'danger')
    
    return redirect(url_for('settings'))

@app.route('/settings/users/<int:user_id>/delete', methods=['POST'])
@login_required
def delete_user(user_id):
    if current_user.role != 'admin':
        flash('Access denied', 'danger')
        return redirect(url_for('settings'))
    
    if user_id == current_user.id:
        flash('Cannot delete your own account', 'warning')
        return redirect(url_for('settings'))
    
    user = User.query.get_or_404(user_id)
    try:
        db.session.delete(user)
        db.session.commit()
        flash('User deleted successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting user: {str(e)}', 'danger')
    
    return redirect(url_for('settings'))

@app.route('/settings/profile', methods=['GET', 'POST'])
@login_required
def profile_settings():
    if request.method == 'POST':
        try:
            current_user.email = request.form['email']
            if request.form.get('password'):
                current_user.set_password(request.form['password'])
            
            db.session.commit()
            flash('Profile updated successfully', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating profile: {str(e)}', 'danger')
    
    return render_template('settings/profile.html')

# Initialize database
def create_tables():
    with app.app_context():
        db.create_all()
        # Create default admin user if not exists
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', email='admin@medisync.com', role='admin')
            admin.set_password('admin123')
            db.session.add(admin)
            
            # Create sample supplier
            supplier = Supplier(
                name="MediSupply Co.",
                contact_person="John Smith",
                email="contact@medisupply.com",
                phone="+1-555-0123",
                address="123 Healthcare Ave, Medical City"
            )
            db.session.add(supplier)
            db.session.commit()
            print("Default admin user created: admin/admin123")

# Initialize the database when the app starts
create_tables()

if __name__ == '__main__':
    app.run(debug=True)