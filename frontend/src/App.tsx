import { BrowserRouter, Link, Route, Routes } from 'react-router-dom';

import AudienceView from './components/AudienceView';
import PresentationList from './components/PresentationList';
import SlideViewer from './components/SlideViewer';

function NotFound() {
  return (
    <div className="status-message">
      <h1>404</h1>
      <p>Page not found.</p>
      <Link to="/">Back to presentations</Link>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<PresentationList />} />
        <Route path="/presentations/:id" element={<SlideViewer />} />
        <Route path="/presentations/:id/audience" element={<AudienceView />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </BrowserRouter>
  );
}
