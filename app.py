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
                supplier_id=request.form.get('supplier_id'),
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
        
        dates.append(date.strftime('%Y-%m-%d'))
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

# Initialize database
@app.before_first_request
def create_tables():
    db.create_all()
    # Create default admin user if not exists
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', email='admin@medisync.com', role='admin')
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()

if __name__ == '__main__':
    app.run(debug=True)