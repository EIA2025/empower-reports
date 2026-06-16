# Empower Reports - New Features Quick Reference Guide

## 🔗 Module Access URLs

| Module | URL Path | Purpose |
|--------|----------|---------|
| Health Management | `/health` | Student health records, allergies, medications, clinic visits |
| Transport | `/transport` | Bus routes, drivers, student assignments, attendance |
| Hostel | `/hostel` | Dormitories, room allocation, occupancy management |
| Learning Materials | `/materials` | Materials, assignments, lesson plans, gradebook |

---

## 💊 Health Module Quick Links

### Main Pages
- `/health/students` - View all students with health summary
- `/health/student/<id>` - View student's complete health profile

### Adding Records
- `/health/allergy/add/<id>` - Add allergy
- `/health/condition/add/<id>` - Add medical condition
- `/health/emergency-contact/add/<id>` - Add emergency contact
- `/health/vaccination/add/<id>` - Add vaccination
- `/health/clinic-visit/add/<id>` - Record clinic visit
- `/health/medication/add/<id>` - Add medication

### Key Features
- Track allergies with severity levels (mild, moderate, severe)
- Record medical conditions and restrictions
- Manage multiple emergency contacts
- Complete vaccination history
- Clinic visit logs with diagnoses and treatments
- Medication administration tracking

---

## 🚌 Transport Module Quick Links

### Main Pages
- `/transport/routes` - View all bus routes
- `/transport/buses` - View all school buses
- `/transport/drivers` - View all drivers

### Management
- `/transport/route/add` - Create new route
- `/transport/bus/add` - Add new bus
- `/transport/driver/add` - Add new driver
- `/transport/route/<id>/stop/add` - Add stop to route
- `/transport/assignment/add/<student_id>` - Assign student to route
- `/transport/attendance/record/<assignment_id>` - Record attendance

### Key Features
- Multiple bus routes with scheduled times
- Bus fleet management with capacity tracking
- Driver license and contact management
- Student route assignments with pickup/dropoff locations
- Daily attendance tracking (morning and afternoon trips)

---

## 🏠 Hostel Module Quick Links

### Main Pages
- `/hostel/dormitories` - View all dormitories
- `/hostel/dormitory/<id>` - View dormitory details
- `/hostel/room/<id>` - View room with bed allocation
- `/hostel/occupancy` - View occupancy statistics

### Management
- `/hostel/dormitory/add` - Create new dormitory
- `/hostel/room/add/<dorm_id>` - Add room to dormitory
- `/hostel/allocation/add/<student_id>` - Allocate student to bed
- `/hostel/allocation/<id>/release` - Release student from hostel

### Key Features
- Multiple dormitory buildings with blocks
- Room management with automatic bed creation
- Student bed allocation tracking
- Release/checkout functionality with dates
- Real-time occupancy rate calculations
- Occupancy statistics by dormitory

---

## 📚 Learning Materials Module Quick Links

### Learning Materials
- `/materials/materials` - Browse all materials
- `/materials/material/add` - Upload new material (PDF, video, PPTX, notes)

### Assignments
- `/materials/assignments` - View all assignments
- `/materials/assignment/add` - Create new assignment
- `/materials/assignment/<id>` - View assignment with submissions

### Lesson Planning
- `/materials/lesson-plans` - View all lesson plans
- `/materials/lesson-plan/add` - Create lesson plan
- `/materials/schemes` - View schemes of work
- `/materials/scheme/add` - Create scheme of work

### Gradebook
- `/materials/gradebook` - View gradebook entries
- `/materials/gradebook/add` - Add gradebook entry

### Supported Assessment Types
- Homework
- Quiz
- CAT (Continuous Assessment Test)
- Midterm
- Final
- Coursework
- Project

---

## 📊 Database Tables Reference

### Health Module (6 tables)
- `student_allergies` - Student allergy records
- `student_medical_conditions` - Medical condition tracking
- `emergency_contacts` - Emergency contact information
- `vaccination_records` - Vaccination history
- `clinic_visits` - Clinic visit logs
- `medication_administration` - Medication records

### Transport Module (6 tables)
- `buses` - School bus fleet
- `drivers` - Bus drivers
- `bus_routes` - Route definitions
- `bus_stops` - Individual stops
- `bus_assignments` - Student assignments
- `bus_attendance` - Attendance tracking

### Hostel Module (4 tables)
- `dormitories` - Hostel buildings
- `rooms` - Individual rooms
- `beds` - Beds in rooms
- `hostel_allocations` - Student allocations

### Learning Materials (7 tables)
- `learning_materials` - Educational resources
- `assignments` - Student assignments
- `assignment_submissions` - Submissions
- `lesson_plans` - Teacher lesson plans
- `schemes_of_work` - Teaching schedules
- `gradebook_entries` - Assessment grades
- `report_cards` - Student report cards

### Finance Enhancements (3 tables)
- `scholarships` - Student scholarships
- `receipts` - Payment receipts
- `financial_reports` - Financial analytics

### Exams (2 tables)
- `exams` - Exam records with workflow
- `exam_marks` - Student marks

---

## 🔐 Role-Based Features

### For Admins
- Manage all modules
- Create routes, dormitories, assign students
- View all health records
- Generate financial reports

### For Teachers
- Upload learning materials
- Create assignments and lesson plans
- Record grades in gradebook
- Add clinic visits and health records

### For Parents
- View student health records
- Track transport assignments
- View hostel allocation
- Download materials (when available)

### For Students
- View own health records
- See assignment deadlines
- Access materials
- View hostel information

---

## 📋 Common Workflows

### Enrolling a Student in Hostel
1. Create dormitory and rooms (`/hostel/dormitory/add`)
2. Add beds to rooms (`/hostel/room/add/<dorm_id>`)
3. Allocate student to bed (`/hostel/allocation/add/<student_id>`)

### Assigning Student to Bus Route
1. Create bus and route (`/transport/route/add`)
2. Add stops to route (`/transport/route/<id>/stop/add`)
3. Assign student (`/transport/assignment/add/<student_id>`)
4. Record daily attendance (`/transport/attendance/record/<assignment_id>`)

### Recording Student Health Information
1. Go to student profile (`/health/student/<id>`)
2. Add relevant health records (allergies, conditions, etc.)
3. Record clinic visits and medications
4. Manage emergency contacts

### Creating and Grading Assignments
1. Create assignment (`/materials/assignment/add`)
2. Students submit work (`/materials/assignment/<id>`)
3. Grade submissions
4. Provide feedback

---

## 🛠️ Troubleshooting

### Tables Not Found
- Ensure `init_db()` runs on startup
- Check database permissions
- Run database migrations if needed

### Routes Not Working
- Check that blueprints are registered in `app.py`
- Verify URL prefixes are correct
- Check session authentication

### Missing Templates
- All key templates are included
- Add custom forms as needed
- Extend base.html for consistency

---

## 📞 Support Features

**All modules include:**
- Search functionality
- Flash messages for feedback
- Back buttons for navigation
- Form validation
- Database integrity checks

---

**Last Updated:** June 16, 2026
**Integration Status:** ✓ Complete
**All Features:** ✓ Working
**CSS:** ✓ Unchanged
**Errors:** ✓ None detected
