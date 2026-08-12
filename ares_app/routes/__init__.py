"""
ARES Modular Flask Blueprints Registration
"""

def register_blueprints(app, state_refs):
    """Registers all modular Flask route blueprints with shared application state references."""
    from ares_app.routes.views import views_bp
    from ares_app.routes.auth_routes import auth_bp
    from ares_app.routes.telemetry_routes import telemetry_bp, init_telemetry_bp
    from ares_app.routes.simulation_routes import simulation_bp, init_simulation_bp
    from ares_app.routes.hardware_routes import hardware_bp, init_hardware_bp
    from ares_app.routes.admin_routes import admin_bp
    from ares_app.routes.ugv_routes import ugv_bp, init_ugv_bp
    from ares_app.routes.reports_routes import reports_bp, init_reports_bp

    init_telemetry_bp(state_refs)
    init_simulation_bp(state_refs)
    init_hardware_bp(state_refs)
    init_ugv_bp(state_refs)
    init_reports_bp(state_refs)

    app.register_blueprint(views_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(telemetry_bp)
    app.register_blueprint(simulation_bp)
    app.register_blueprint(hardware_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(ugv_bp)
    app.register_blueprint(reports_bp)
