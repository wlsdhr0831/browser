// var div = document.createElement("div");
// var div2 = document.createElement("div");

// console.log(div);

// var div3 = document.querySelectorAll("div")[0];

var a = document.querySelectorAll("div")[0];
var b = document.querySelectorAll("span")[0];

console.log("?????")
console.log(a);
console.log(a.children);
console.log(b);

var removed = a.removeChild(b);

console.log(removed === b);      // true
console.log(a.children.length); // 0
console.log(b.children);        // 정상 (subtree 유지)
