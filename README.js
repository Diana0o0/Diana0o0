class Task {
  constructor(name) {
    this.name = name;
    this.closed = false;
  }

  close() {
    this.closed = true;
    console.log(`Task "${this.name}" has been closed.`);
  }

  status() {
    return this.closed ? 'closed' : 'open';
  }
}

const hiTask = new Task('Hi');
console.log(`Task "${hiTask.name}" is ${hiTask.status()}.`);
hiTask.close();
console.log(`Task "${hiTask.name}" is now ${hiTask.status()}.`);
