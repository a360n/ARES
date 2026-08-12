import threading

class ARESConcurrencyManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(ARESConcurrencyManager, cls).__new__(cls)
                cls._instance._init_manager()
            return cls._instance

    def _init_manager(self):
        self.lock = threading.Lock()
        # Seat 1 is strictly for Admin. Seats 2, 3, 4 are dynamic for Operator or Observer.
        self.seats = {
            1: None,
            2: None,
            3: None,
            4: None
        }
        self.sid_to_seat = {}

    def request_seat(self, user, sid):
        """
        Attempts to assign a seat to an authenticated user connection.
        Returns the assigned seat ID (1-4) on success, or None on failure/capacity limit.
        """
        with self.lock:
            # 1. Prevent duplicate logins: check if this user is already seated
            for seat_id, seated in self.seats.items():
                if seated and seated["username"] == user.username:
                    print(f"[Concurrency Manager] User '{user.username}' is already seated in Seat {seat_id}. Rejecting duplicate connection.")
                    return None

            # 2. Allocate seat
            if user.user_type == "Admin":
                # Admin strictly claims Seat 1
                if self.seats[1] is None:
                    self.seats[1] = {
                        "username": user.username,
                        "user_type": user.user_type,
                        "operator_points": user.operator_points,
                        "sid": sid,
                        "assigned_role": "Admin"
                    }
                    self.sid_to_seat[sid] = 1
                    self._recalculate_hierarchy_unlocked()
                    print(f"[Concurrency Manager] Admin seated in Seat 1 (Session: {sid}).")
                    return 1
                else:
                    print("[Concurrency Manager] Seat 1 (Admin) is already occupied. Rejecting connection.")
                    return None
            else:
                # Operators and Observers sit in dynamic Seats 2, 3, 4
                for seat_id in [2, 3, 4]:
                    if self.seats[seat_id] is None:
                        self.seats[seat_id] = {
                            "username": user.username,
                            "user_type": user.user_type,
                            "operator_points": user.operator_points,
                            "sid": sid,
                            "assigned_role": "Observer" if user.user_type == "Observer" else None
                        }
                        self.sid_to_seat[sid] = seat_id
                        self._recalculate_hierarchy_unlocked()
                        print(f"[Concurrency Manager] User '{user.username}' ({user.user_type}) seated in Seat {seat_id} (Session: {sid}).")
                        return seat_id
                print("[Concurrency Manager] Dynamic seats (2-4) are fully occupied. Rejecting connection.")
                return None

    def release_seat(self, sid):
        """
        Releases the seat occupied by session ID `sid`.
        """
        with self.lock:
            seat_id = self.sid_to_seat.get(sid)
            if seat_id:
                print(f"[Concurrency Manager] Releasing Seat {seat_id} for session {sid}.")
                self.seats[seat_id] = None
                del self.sid_to_seat[sid]
                self._recalculate_hierarchy_unlocked()
                return seat_id
            return None

    def get_user_by_sid(self, sid):
        """
        Retrieves the seated user dictionary for the given session ID.
        """
        with self.lock:
            seat_id = self.sid_to_seat.get(sid)
            if seat_id:
                return self.seats[seat_id]
            return None

    def get_seats_status(self):
        """
        Returns a copy of the current seats occupancy state.
        """
        with self.lock:
            return {seat_id: (seated.copy() if seated else None) for seat_id, seated in self.seats.items()}

    def _recalculate_hierarchy_unlocked(self):
        """
        Determines the Primary/Backup operator roles based on points.
        Must be called from within the self.lock boundary.
        """
        # Find all active dynamic seats occupied by Operators
        operators_in_seats = []
        for seat_id in [2, 3, 4]:
            seated = self.seats[seat_id]
            if seated and seated["user_type"] == "Operator":
                operators_in_seats.append((seat_id, seated))

        if not operators_in_seats:
            return

        # Sort operators by points descending, with seat_id as tiebreaker (smaller first)
        operators_in_seats.sort(key=lambda x: (x[1]["operator_points"], -x[0]), reverse=True)

        # The highest ranking operator is designated Primary, all others are Backup
        operators_in_seats[0][1]["assigned_role"] = "Primary_Operator"
        for _, seated in operators_in_seats[1:]:
            seated["assigned_role"] = "Backup_Operator"

concurrency_manager = ARESConcurrencyManager()
