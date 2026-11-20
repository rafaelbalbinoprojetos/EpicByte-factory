import {render, screen} from '@testing-library/react';
import {App} from './App';

it('renderiza o título principal', () => {
  render(<App />);
  expect(screen.getByRole('heading', {level: 1})).toBeInTheDocument();
});
