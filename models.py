from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class AppUser(db.Model):
    __tablename__ = 'app_users'
    id       = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

    def set_password(self, pw):
        self.password = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password, pw)


class Client(db.Model):
    __tablename__ = 'clients'
    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(50), nullable=False)       # 何小名
    name_masked = db.Column(db.String(50), nullable=False)       # 何O名
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    positions   = db.relationship('Position', back_populates='client', lazy=True)

    @staticmethod
    def mask_name(name):
        if not name or len(name) < 2:
            return name
        return name[0] + 'O' + name[2:]


class Product(db.Model):
    __tablename__ = 'products'
    id             = db.Column(db.Integer, primary_key=True)
    product_code   = db.Column(db.String(20), unique=True, nullable=False)
    issuer         = db.Column(db.String(20))
    product_type   = db.Column(db.String(10), default='FCN')
    tenor_months   = db.Column(db.Integer)
    currency       = db.Column(db.String(5), default='USD')
    coupon_rate    = db.Column(db.Float)                          # 0.12 = 12%
    trade_date     = db.Column(db.Date)
    start_date     = db.Column(db.Date)                          # 比價日
    maturity_date  = db.Column(db.Date)                          # 期末訂價日
    ko_pct         = db.Column(db.Float)                         # 1.00 = 100%
    strike_pct     = db.Column(db.Float)
    eki_pct        = db.Column(db.Float)                         # None = 無EKI
    ko_type        = db.Column(db.String(20), default='fixed')   # fixed / stepdown
    special_notes  = db.Column(db.Text)
    status         = db.Column(db.String(20), default='active')  # active / ko_exited / matured
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)
    underlyings    = db.relationship('Underlying', back_populates='product',
                                     cascade='all, delete-orphan', lazy=True)
    positions      = db.relationship('Position', back_populates='product', lazy=True)

    @property
    def days_to_maturity(self):
        if self.maturity_date:
            return (self.maturity_date - date.today()).days
        return None

    @property
    def all_ko_hit(self):
        uls = [u for u in self.underlyings if u.initial_price]
        return len(uls) > 0 and all(u.ko_hit for u in uls)


class Underlying(db.Model):
    __tablename__ = 'underlyings'
    id             = db.Column(db.Integer, primary_key=True)
    product_id     = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    ticker         = db.Column(db.String(20), nullable=False)
    initial_price  = db.Column(db.Float)
    ko_level       = db.Column(db.Float)
    strike_level   = db.Column(db.Float)
    eki_level      = db.Column(db.Float)
    ko_hit         = db.Column(db.Boolean, default=False)
    latest_price   = db.Column(db.Float)
    price_date     = db.Column(db.Date)
    position_order = db.Column(db.Integer)
    product        = db.relationship('Product', back_populates='underlyings')


class Position(db.Model):
    __tablename__ = 'positions'
    id                = db.Column(db.Integer, primary_key=True)
    client_id         = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    product_id        = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    investment_amount = db.Column(db.Float)                      # USD金額
    notes             = db.Column(db.Text)
    created_at        = db.Column(db.DateTime, default=datetime.utcnow)
    client            = db.relationship('Client', back_populates='positions')
    product           = db.relationship('Product', back_populates='positions')

    @property
    def monthly_coupon(self):
        if self.investment_amount and self.product and self.product.coupon_rate:
            return round(self.investment_amount * self.product.coupon_rate / 12, 2)
        return None


class PriceHistory(db.Model):
    __tablename__ = 'price_history'
    id             = db.Column(db.Integer, primary_key=True)
    underlying_id  = db.Column(db.Integer, db.ForeignKey('underlyings.id'), nullable=False)
    price_date     = db.Column(db.Date, nullable=False)
    closing_price  = db.Column(db.Float)
    ko_triggered   = db.Column(db.Boolean, default=False)
    __table_args__ = (db.UniqueConstraint('underlying_id', 'price_date'),)
