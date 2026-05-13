# Strategic War Room v2.0 - Professional Trading Dashboard

Professional-grade trading analytics dashboard built with React 18, TypeScript, and Tailwind CSS.

## Features

- **Enhanced Signal Analysis**: Complete trade metrics including pip calculations, position sizing, profit projections
- **Multi-Target Planning**: Automatic 3-tier profit-taking system (TP1 33%, TP2 66%, TP3 100%)
- **Risk Management**: Position sizing based on account balance and risk percentage
- **Trade Quality Scoring**: AI-powered trade quality metrics (0-100 scale)
- **Real-Time Calculations**: Instant profit/loss simulations and margin calculations
- **Professional UI**: TradingView-style dark theme with smooth animations
- **Responsive Design**: Works seamlessly on desktop, tablet, and mobile devices

## Tech Stack

- **React 18** - UI framework
- **TypeScript** - Type-safe development
- **Tailwind CSS** - Utility-first styling
- **Framer Motion** - Smooth animations
- **Recharts** - Data visualization
- **Lucide React** - Icon library
- **Axios** - HTTP client
- **Vite** - Build tool

## Project Structure

```
frontend_v2/
├── src/
│   ├── components/
│   │   └── EnhancedSignalCard.tsx    # Main signal display component
│   ├── services/
│   │   └── api.ts                     # API client
│   ├── types.ts                       # TypeScript type definitions
│   ├── App.tsx                        # Main application component
│   ├── main.tsx                       # Application entry point
│   └── index.css                      # Global styles with Tailwind
├── index.html                         # HTML template
├── package.json                       # Dependencies and scripts
├── tsconfig.json                      # TypeScript configuration
├── vite.config.ts                     # Vite build configuration
├── tailwind.config.js                 # Tailwind CSS configuration
└── postcss.config.js                  # PostCSS configuration
```

## Setup Instructions

### 1. Install Dependencies

```bash
cd frontend_v2
npm install
```

### 2. Development Server

```bash
npm run dev
```

The application will be available at `http://localhost:3000`

### 3. Build for Production

```bash
npm run build
```

The built files will be in the `dist` directory.

### 4. Preview Production Build

```bash
npm run preview
```

## Configuration

The API client is configured to connect to `http://localhost:8000` by default. To change this, edit `src/services/api.ts`:

```typescript
const API_BASE = 'http://localhost:8000'
```

## Features Explained

### Enhanced Signal Card

The main component displaying comprehensive trade analysis:

- **Header**: Pair name, position type (LONG/SHORT), quality score
- **Main Metrics**: Risk-reward ratio and AI confidence level
- **Pip Analysis**: Target and stop-loss pip calculations
- **Price Levels**: Entry, target, and stop-loss prices
- **Multi-Target Plan**: Three-tier profit-taking levels (TP1, TP2, TP3)
- **Profit/Loss Simulation**: Estimated profits and ROI
- **Position Sizing**: Recommended lot size and margin requirements
- **Risk Assessment**: Quality score, strength rating, volatility level, and risk level

### API Integration

The dashboard connects to the backend API for:

- `/api/calculate/enhanced-signal` - Complete trade analysis
- `/api/signals/enhanced-history` - Historical signal data
- `/api/prices` - Current market prices

## Responsive Design

- **Mobile**: Single column layout with touch-optimized inputs
- **Tablet**: Two-column layout with medium spacing
- **Desktop**: Full multi-column grid with maximum information density

## Browser Support

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+
- Mobile browsers (iOS Safari, Chrome Mobile)

## Performance

- Lightweight bundle size (~100KB gzipped)
- Optimized re-renders with React hooks
- Smooth 60fps animations with Framer Motion
- Lazy loading for historical signals

## Customization

### Theme Colors

Edit `tailwind.config.js` to customize color scheme:

```javascript
theme: {
  extend: {
    colors: {
      // Add custom colors here
    },
  },
},
```

### Animation Speed

Modify animation durations in component files:

```typescript
transition={{ delay: idx * 0.1 }}
```

## Future Enhancements

- [ ] Advanced charting with Recharts
- [ ] Real-time WebSocket updates
- [ ] Portfolio performance tracking
- [ ] Trade history export (CSV/PDF)
- [ ] Dark/Light theme toggle
- [ ] Customizable dashboard layouts
- [ ] Historical performance charts
- [ ] Alert notifications

## Contributing

This is a professional trading dashboard. Please maintain code quality standards:

- Use TypeScript for type safety
- Follow existing code style
- Add comments for complex logic
- Test responsive design on mobile

## License

Proprietary - Strategic War Room v2.0

## Support

For issues or questions, refer to the main project documentation.
