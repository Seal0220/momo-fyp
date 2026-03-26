export function EventLog({ items }: { items: string[] }) {
  return (
    <section className="panel">
      <div className="panel-header">
        <h3>Events</h3>
      </div>
      <div className="event-log">
        {items.length === 0 ? <p>No events yet.</p> : items.map((item, index) => <p key={`${item}-${index}`}>{item}</p>)}
      </div>
    </section>
  );
}

