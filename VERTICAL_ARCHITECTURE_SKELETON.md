# Multi-Vertical Architecture - Skeleton Created

## Overview
Created a scalable, multi-vertical architecture to support Private Equity (PE) and Real Estate (RE) domains with shared core functionality. This structure supports future microservices conversion.

## Backend Structure Created

### Directory Layout
```
backend/
├── app/
│   ├── config/
│   │   └── verticals.py          ✅ Vertical configuration (PE & RE)
│   │
│   ├── core/                      ✅ Shared modules (all verticals use this)
│   │   ├── documents/
│   │   ├── chat/
│   │   ├── auth/
│   │   ├── embeddings/
│   │   └── llm_clients/
│   │
│   ├── verticals/                 ✅ Domain-specific modules
│   │   ├── private_equity/
│   │   │   ├── api/
│   │   │   │   └── router.py      ✅ /api/v1/pe/* routes
│   │   │   ├── workflows/         (To be moved)
│   │   │   ├── extraction/        (To be implemented)
│   │   │   └── comparison/        (Future feature)
│   │   │
│   │   └── real_estate/
│   │       ├── api/
│   │       │   └── router.py      ✅ /api/v1/re/* routes
│   │       ├── excel_templates/   (To be implemented)
│   │       └── template_filling/  (To be implemented)
│   │
│   └── migrations/
│       └── versions/
│           └── 8af61ecfd7fa_add_vertical_column_to_users.py  ✅
│
└── docker-compose.yml
```

### Database Changes
- **Added** `vertical` column to `users` table
  - Type: `String(50)`
  - Default: `'private_equity'` (backward compatible)
  - Indexed for fast lookups
- **Migration**: `8af61ecfd7fa_add_vertical_column_to_users`

### Configuration System
**File**: `app/config/verticals.py`

Functions available:
- `get_vertical_config(vertical)` - Get full config for a vertical
- `get_vertical_features(vertical)` - Get list of enabled features
- `is_feature_enabled(vertical, feature)` - Check if feature is enabled

**Features Defined**:
```python
private_equity: [
    'document_library',
    'free_form_chat',
    'workflows',
    'extraction',
    'comparison',  # Future
]

real_estate: [
    'document_library',
    'free_form_chat',
    'excel_templates',
    'template_filling',
]
```

### API Routes (Ready for Integration)
- **PE Routes**: `/api/v1/pe/*`
  - Health check: `/api/v1/pe/health` ✅
- **RE Routes**: `/api/v1/re/*`
  - Health check: `/api/v1/re/health` ✅

**Next Step**: Integrate these routers into `app/main.py`:
```python
from app.verticals.private_equity.api.router import router as pe_router
from app.verticals.real_estate.api.router import router as re_router

app.include_router(pe_router, prefix="/api/v1")
app.include_router(re_router, prefix="/api/v1")
```

---

## Frontend Structure Created

### Directory Layout
```
frontend/src/
├── config/
│   └── verticals.js              ✅ Vertical configuration
│
├── core/                          ✅ Shared across all verticals
│   ├── hooks/
│   │   ├── useVertical.js        ✅ Custom hook for vertical context
│   │   └── index.js
│   ├── components/
│   └── utils/
│
├── verticals/                     ✅ Domain-specific modules
│   ├── private_equity/
│   │   ├── pages/
│   │   │   ├── Dashboard.jsx     ✅ PE dashboard (placeholder)
│   │   │   └── index.js
│   │   ├── components/           (To be created)
│   │   ├── hooks/                (To be created)
│   │   └── index.js
│   │
│   ├── real_estate/
│   │   ├── pages/
│   │   │   ├── Dashboard.jsx     ✅ RE dashboard (placeholder)
│   │   │   └── index.js
│   │   ├── components/           (To be created)
│   │   ├── hooks/                (To be created)
│   │   └── index.js
│   │
│   └── index.js
│
└── routes/
    └── verticalRoutes.jsx        ✅ Vertical routing setup
```

### Configuration System
**File**: `src/config/verticals.js`

Functions available:
```javascript
getVerticalConfig(vertical)       // Get full config
isFeatureEnabled(vertical, feature)
getVerticalNavigation(vertical)
getAllVerticals()
getVerticalTheme(vertical)
```

### Custom Hook
**File**: `src/core/hooks/useVertical.js`

Usage in components:
```javascript
import { useVertical } from '../core/hooks/useVertical';

function MyComponent() {
  const { vertical, config, isFeatureEnabled, pathPrefix } = useVertical();

  if (isFeatureEnabled('workflows')) {
    return <WorkflowsComponent />;
  }
}
```

### Routing Setup
**File**: `src/routes/verticalRoutes.jsx`

Routes created:
```
/pe                    → PE Dashboard
/pe/library           → Document Library (shared)
/pe/chat              → Chat Interface (shared)
/pe/workflows         → Workflow Execution
/pe/extraction        → Document Extraction
/pe/comparison        → Document Comparison (coming soon)

/re                    → RE Dashboard
/re/library           → Document Library (shared)
/re/chat              → Chat Interface (shared)
/re/templates         → Excel Templates
/re/fills             → Template Fills
```

**Integration in App.jsx**:
```javascript
import { verticalRoutes } from './routes/verticalRoutes';

// In your router setup:
<Routes>
  {verticalRoutes.map(route => <Route key={route.path} {...route} />)}
</Routes>
```

---

## Next Steps (Detailed Roadmap)

### Phase 1: Move Existing PE Code (In Progress)
- [ ] Move `app/services/workflows/private_equity/` → `app/verticals/private_equity/workflows/`
- [ ] Update all imports in workflow code
- [ ] Move extraction services to `app/verticals/private_equity/extraction/`
- [ ] Create API routers for PE workflows and extraction

### Phase 2: Identify & Move Shared Code
- [ ] Audit `app/services/` for shared functionality
- [ ] Move document management to `app/core/documents/`
- [ ] Move chat engine to `app/core/chat/`
- [ ] Move embeddings to `app/core/embeddings/`
- [ ] Create wrapper functions in PE module to maintain compatibility

### Phase 3: Update API Routes
- [ ] Create workflow routers in `app/verticals/private_equity/api/workflows.py`
- [ ] Create extraction routers in `app/verticals/private_equity/api/extraction.py`
- [ ] Update main FastAPI app to include vertical routers
- [ ] Add middleware to validate user vertical access

### Phase 4: Frontend Integration
- [ ] Move existing PE components to `src/verticals/private_equity/components/`
- [ ] Create shared components in `src/core/components/`
- [ ] Update routing to use verticalRoutes
- [ ] Test vertical switching and feature flags

### Phase 5: Add Real Estate Features
- [ ] Create Excel template models in backend
- [ ] Implement template filling service
- [ ] Create RE API routes
- [ ] Build RE frontend pages and components

---

## Key Design Decisions

1. **User-based Vertical Assignment** (For Now)
   - Vertical stored in `users.vertical` column
   - Future: Evolve to organization-based multi-tenancy
   - Backward compatible: Defaults to 'private_equity'

2. **Shared vs. Vertical-Specific Code**
   - **Shared** (in `core/`): Documents, Chat, Auth, Embeddings, LLM
   - **Vertical-Specific**: Workflows, Extraction, Excel templates, Domain-specific UIs

3. **API Structure**
   - `/api/v1/pe/*` for PE routes
   - `/api/v1/re/*` for RE routes
   - Shared routes: `/api/v1/documents`, `/api/v1/chat`

4. **Database Strategy**
   - Single shared database for now
   - `domain` columns in vertical-specific tables for future separation
   - Can evolve to separate databases per vertical if needed

5. **Microservices Ready**
   - Each vertical is already loosely coupled
   - API boundaries clearly defined
   - Can be extracted to separate services later

---

## How to Continue

### For Moving PE Code:
```bash
# 1. Copy existing PE workflows
cp -r backend/app/services/workflows/private_equity/* \
      backend/app/verticals/private_equity/workflows/

# 2. Fix imports (update paths to reference new locations)
# 3. Create API routers
# 4. Test
```

### For Creating RE Features:
```bash
# 1. Create models for excel_templates
backend/app/verticals/real_estate/models.py

# 2. Create template filling service
backend/app/verticals/real_estate/template_filling/service.py

# 3. Create API routes
backend/app/verticals/real_estate/api/templates.py
backend/app/verticals/real_estate/api/fills.py

# 4. Create frontend pages
frontend/src/verticals/real_estate/pages/TemplatesPage.jsx
frontend/src/verticals/real_estate/pages/TemplateFillsPage.jsx
```

---

## Files Created

### Backend
- ✅ `app/config/verticals.py` - Configuration system
- ✅ `app/verticals/__init__.py` - Vertical modules entry
- ✅ `app/verticals/private_equity/__init__.py`
- ✅ `app/verticals/private_equity/api/router.py` - PE router
- ✅ `app/verticals/real_estate/__init__.py`
- ✅ `app/verticals/real_estate/api/router.py` - RE router
- ✅ `app/core/**/__init__.py` - Core module placeholders
- ✅ `migrations/8af61ecfd7fa_add_vertical_column_to_users.py` - Migration (applied)

### Frontend
- ✅ `src/config/verticals.js` - Configuration system
- ✅ `src/core/hooks/useVertical.js` - Custom hook
- ✅ `src/verticals/private_equity/pages/Dashboard.jsx`
- ✅ `src/verticals/real_estate/pages/Dashboard.jsx`
- ✅ `src/routes/verticalRoutes.jsx` - Routing setup
- ✅ Various `index.js` files for module exports

### Documentation
- ✅ `VERTICAL_ARCHITECTURE_SKELETON.md` - This file

---

## Testing the Skeleton

### Backend
```bash
# Start containers
docker-compose up

# Test PE health check
curl http://localhost:8000/api/v1/pe/health

# Test RE health check
curl http://localhost:8000/api/v1/re/health
```

### Frontend
```bash
# Import and use the hooks
import { useVertical } from './core/hooks/useVertical';

// In a component:
const { vertical, config, isFeatureEnabled } = useVertical();
console.log(vertical);  // 'private_equity' or 'real_estate'
console.log(config.name);  // 'Private Equity' or 'Real Estate'
```

---

## Questions & Next Actions

1. **Ready to move PE code to new structure?**
   - Would you like me to start copying workflows and updating imports?

2. **Backend API integration?**
   - Should I update the main FastAPI app to include the vertical routers?

3. **Frontend routing?**
   - Should I help integrate the verticalRoutes into your App.jsx?

4. **Priority on RE features?**
   - Should we start building Excel template functionality next?
