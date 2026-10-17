import { render } from '@testing-library/react';
import { App } from '../App';
import { SoundMatClient } from '../api/client';
import { ClientProvider } from '../api/context';

export function setup() {
  const client = new SoundMatClient('http://test');
  const posts: [string, unknown][] = [];
  client.post = async (path: string, body?: unknown) => {
    posts.push([path, body]);
    return {};
  };
  const view = render(
    <ClientProvider client={client}>
      <App />
    </ClientProvider>,
  );
  return { client, posts, view };
}
